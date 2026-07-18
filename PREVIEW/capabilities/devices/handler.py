"""devices.sync durable worker handler（Intune 受管裝置）。

結構比照 app/capabilities/accounts/handler.py：page checkpoint、Graph 例外正確轉譯
（尊重 Retry-After、401/403 立即 dead-letter 並將 connection 降級）、full-sync finalize。
差異僅在 Graph 資源路徑與 $select 欄位。
"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capabilities.devices.models import DeviceSyncCheckpoint
from app.capabilities.devices.service import DeviceSyncService
from app.jobs.queue import PgJobQueue
from app.jobs.worker import RetryableJobError, TerminalJobError
from app.microsoft.graph_client import GraphClient, GraphRetryableError, GraphTerminalError
from app.microsoft.models import TenantConnection
from app.storage.time_utils import utc_now_naive

_DEVICES_RESOURCE = "/deviceManagement/managedDevices"
_DEVICES_SELECT = (
    "id,deviceName,operatingSystem,osVersion,complianceState,"
    "managedDeviceOwnerType,userPrincipalName,serialNumber,lastSyncDateTime"
)

# 見 accounts/handler.py：權限撤銷／credential 過期須讓 Tenant connection 轉 degraded。
_CONNECTION_DEGRADING_CODES = frozenset({"graph_authorization_failed"})


class DevicesSyncHandler:
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
            select(DeviceSyncCheckpoint).where(
                DeviceSyncCheckpoint.job_id == job_id,
                DeviceSyncCheckpoint.environment_id == environment_id,
                DeviceSyncCheckpoint.managed_tenant_id == managed_tenant_id,
            )
        ).scalar_one_or_none()
        if checkpoint is not None and checkpoint.status == "completed":
            return
        if checkpoint is None:
            checkpoint = DeviceSyncCheckpoint(
                job_id=job_id,
                environment_id=environment_id,
                managed_tenant_id=managed_tenant_id,
                next_resource=_DEVICES_RESOURCE,
                processed_count=0,
                status="running",
            )
            self.session.add(checkpoint)
            self.session.flush()

        client = self.graph_client_factory(environment_id, managed_tenant_id)
        service = DeviceSyncService(
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
                    params={"$select": _DEVICES_SELECT} if resource == _DEVICES_RESOURCE else None,
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

            devices = response.get("value")
            if not isinstance(devices, list):
                raise TerminalJobError("graph_response_invalid")
            try:
                processed = service.upsert_page(devices)
            except ValueError as exc:
                raise TerminalJobError("graph_device_invalid") from exc
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
