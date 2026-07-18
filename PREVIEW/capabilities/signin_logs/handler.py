"""signin_logs.sync durable worker handler（Entra 登入記錄，watermark 增量）。

與 accounts/devices handler 的差異（roadmap Phase B3）：
- 首頁以 `$filter=createdDateTime ge <watermark>` 只抓比上次更新的資料（時間區間查詢）。
- watermark 於 checkpoint 建立時算一次並存入 `window_start`；resume 時用它重建 filter，不重算
  （避免跨頁時 watermark 隨已 commit 的資料前移，造成邊界資料被跳過）。
- 首次同步（無既有資料）退回「最近 24 小時」初始視窗，控制資料量。
- **完成後不做 finalize/刪除**——登入記錄 append-only。用 `ge` + 冪等 upsert，邊界資料重抓也不重複。
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable
from urllib.parse import urlparse
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capabilities.signin_logs.models import SignInLogSyncCheckpoint
from app.capabilities.signin_logs.service import SignInLogSyncService, to_graph_filter_iso
from app.jobs.queue import PgJobQueue
from app.jobs.worker import RetryableJobError, TerminalJobError
from app.microsoft.graph_client import GraphClient, GraphRetryableError, GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive

_SIGNINS_RESOURCE = "/auditLogs/signIns"
_SIGNINS_SELECT = (
    "id,createdDateTime,userPrincipalName,userDisplayName,appDisplayName,"
    "ipAddress,clientAppUsed,conditionalAccessStatus,status"
)
_PAGE_SIZE = 200
_INITIAL_WINDOW_HOURS = 24

# 見 accounts/handler.py：權限撤銷／credential 過期須讓 Tenant connection 轉 degraded。
_CONNECTION_DEGRADING_CODES = frozenset({"graph_authorization_failed"})


class SignInLogsSyncHandler:
    def __init__(
        self,
        session: Session,
        graph_client_factory: Callable[[uuid.UUID, uuid.UUID], GraphClient],
    ) -> None:
        self.session = session
        self.graph_client_factory = graph_client_factory

    async def handle(
        self,
        envelope,
        *,
        queue: PgJobQueue,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        job_id = uuid.UUID(envelope["message_id"])
        environment_id = uuid.UUID(envelope["environment_id"])
        managed_tenant_id = uuid.UUID(envelope["managed_tenant_id"])
        service = SignInLogSyncService(
            self.session,
            environment_id=environment_id,
            managed_tenant_id=managed_tenant_id,
            sync_id=job_id,
        )

        checkpoint = self.session.execute(
            select(SignInLogSyncCheckpoint).where(
                SignInLogSyncCheckpoint.job_id == job_id,
                SignInLogSyncCheckpoint.environment_id == environment_id,
                SignInLogSyncCheckpoint.managed_tenant_id == managed_tenant_id,
            )
        ).scalar_one_or_none()
        if checkpoint is not None and checkpoint.status == "completed":
            return
        if checkpoint is None:
            # watermark 只在此算一次並釘進 window_start；resume 時沿用，不重算（見 module docstring）。
            watermark = service.watermark()
            if watermark is None:
                watermark = utc_now_naive() - timedelta(hours=_INITIAL_WINDOW_HOURS)
            checkpoint = SignInLogSyncCheckpoint(
                job_id=job_id,
                environment_id=environment_id,
                managed_tenant_id=managed_tenant_id,
                window_start=to_graph_filter_iso(watermark),
                next_resource=_SIGNINS_RESOURCE,
                processed_count=0,
                status="running",
            )
            self.session.add(checkpoint)
            self.session.flush()

        client = self.graph_client_factory(environment_id, managed_tenant_id)
        while checkpoint.next_resource:
            resource = checkpoint.next_resource
            self._validate_resource(resource)
            try:
                response = await client.get(
                    resource,
                    params=self._first_page_params(checkpoint.window_start)
                    if resource == _SIGNINS_RESOURCE else None,
                )
            except GraphRetryableError as exc:
                # 保留 GraphClient 已解析的 Retry-After，不得改用固定延遲蓋掉它（04 §7）。
                raise RetryableJobError(exc.code, delay_seconds=exc.retry_after) from exc
            except GraphTerminalError as exc:
                if exc.code in _CONNECTION_DEGRADING_CODES:
                    self._degrade_connection(managed_tenant_id)
                    self.session.commit()
                raise TerminalJobError(exc.code) from exc
            except (RetryableJobError, TerminalJobError):
                raise
            except Exception as exc:
                raise RetryableJobError("graph_request_failed", delay_seconds=30) from exc

            sign_ins = response.get("value")
            if not isinstance(sign_ins, list):
                raise TerminalJobError("graph_response_invalid")
            try:
                processed = service.upsert_page(sign_ins)
            except ValueError as exc:
                raise TerminalJobError("graph_signin_invalid") from exc
            next_resource = response.get("@odata.nextLink")
            if next_resource is not None and not isinstance(next_resource, str):
                raise TerminalJobError("graph_next_link_invalid")
            checkpoint.processed_count += processed
            checkpoint.next_resource = next_resource
            checkpoint.updated_at = utc_now_naive()
            queue.heartbeat(
                envelope["message_id"], worker_id=worker_id, lease_seconds=lease_seconds,
            )
            self.session.commit()

        # append-only：完成即結束，不做刪除 finalize。
        checkpoint.status = "completed"
        checkpoint.completed_at = utc_now_naive()
        checkpoint.updated_at = checkpoint.completed_at
        self.session.commit()

    @staticmethod
    def _first_page_params(window_start: str | None) -> dict:
        params = {
            "$orderby": "createdDateTime",
            "$top": _PAGE_SIZE,
            "$select": _SIGNINS_SELECT,
        }
        if window_start:
            # `ge`（>=）而非 `gt`：搭配 (tenant, id) 冪等 upsert，邊界同秒事件重抓也不漏不重。
            params["$filter"] = f"createdDateTime ge {window_start}"
        return params

    @staticmethod
    def _validate_resource(resource: str) -> None:
        parsed = urlparse(resource)
        if resource.startswith("/"):
            return
        if parsed.scheme != "https" or parsed.netloc.lower() != "graph.microsoft.com":
            raise TerminalJobError("graph_next_link_not_allowed")

    def _degrade_connection(self, managed_tenant_id: uuid.UUID) -> None:
        connection = self.session.execute(
            select(TenantConnection).where(TenantConnection.managed_tenant_id == managed_tenant_id)
        ).scalar_one_or_none()
        if connection is not None and connection.status == "active":
            connection.status = "degraded"
            connection.updated_at = utc_now_naive()
