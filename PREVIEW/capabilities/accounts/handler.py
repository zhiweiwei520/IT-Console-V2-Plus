"""accounts.sync durable worker handler。"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capabilities.accounts.models import AccountSyncCheckpoint
from app.capabilities.accounts.service import AccountSyncService
from app.jobs.queue import PgJobQueue
from app.jobs.worker import RetryableJobError, TerminalJobError
from app.microsoft.graph_client import GraphClient, GraphRetryableError, GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive

# GraphTerminalError code 對應 04-microsoft-connection-and-consent.md §7：
# 權限撤銷／credential 過期是永久或半永久錯誤，須讓 Tenant connection 轉 degraded，
# 不能只靠 dead-letter 一次性訊息，否則下次排程還是會重新無限重試。
_CONNECTION_DEGRADING_CODES = frozenset({"graph_authorization_failed"})


class AccountsSyncHandler:
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
        checkpoint = self.session.execute(
            select(AccountSyncCheckpoint).where(
                AccountSyncCheckpoint.job_id == job_id,
                AccountSyncCheckpoint.environment_id == environment_id,
                AccountSyncCheckpoint.managed_tenant_id == managed_tenant_id,
            )
        ).scalar_one_or_none()
        if checkpoint is not None and checkpoint.status == "completed":
            return
        if checkpoint is None:
            checkpoint = AccountSyncCheckpoint(
                job_id=job_id,
                environment_id=environment_id,
                managed_tenant_id=managed_tenant_id,
                next_resource="/users",
                processed_count=0,
                status="running",
            )
            self.session.add(checkpoint)
            self.session.flush()

        client = self.graph_client_factory(environment_id, managed_tenant_id)
        service = AccountSyncService(
            self.session,
            environment_id=environment_id,
            managed_tenant_id=managed_tenant_id,
            sync_id=job_id,
        )
        while checkpoint.next_resource:
            resource = checkpoint.next_resource
            self._validate_resource(resource)
            try:
                response = await client.get(
                    resource,
                    params={
                        "$select": "id,displayName,userPrincipalName,accountEnabled",
                    } if resource == "/users" else None,
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

            users = response.get("value")
            if not isinstance(users, list):
                raise TerminalJobError("graph_response_invalid")
            try:
                processed = service.upsert_page(users)
            except ValueError as exc:
                raise TerminalJobError("graph_user_invalid") from exc
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

        service.finalize_full_sync()
        checkpoint.status = "completed"
        checkpoint.completed_at = utc_now_naive()
        checkpoint.updated_at = checkpoint.completed_at
        self.session.commit()

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
