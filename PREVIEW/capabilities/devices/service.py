"""
devices service。

Web 查詢 service、Worker page upsert service，以及 manage.py demo seed helper。
Graph I/O 位於 handler.py，透過 app/microsoft/graph_client.py protocol 注入（比照 accounts）。
"""
from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.capabilities.devices.models import Device
from app.capabilities.devices.repository import DeviceRepository
from app.storage.tenant_context import TenantContext


def _clean(value) -> str | None:
    """Graph 缺值可能是 None 或空字串；統一正規化為 None 或 strip 後的字串。"""
    text = str(value).strip() if value is not None else ""
    return text or None


class DeviceService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.repository = DeviceRepository(session, context)

    def list_devices(self) -> list[Device]:
        if not self.context.has_permission("devices.view"):
            raise PermissionError("devices.view required")
        return self.repository.list_devices()


class DeviceSyncService:
    """Worker 專用同步服務；scope 必須由已重驗證的 environment/tenant 顯式傳入。"""

    def __init__(self, session: Session, *, environment_id, managed_tenant_id, sync_id) -> None:
        self.session = session
        self.environment_id = environment_id
        self.managed_tenant_id = managed_tenant_id
        self.sync_id = sync_id

    def upsert_page(self, devices: list[dict]) -> int:
        processed = 0
        for raw in devices:
            source_id = str(raw.get("id") or "").strip()
            if not source_id:
                # Intune 裝置唯一必要欄位是 id；缺 id 代表回應異常，屬永久錯誤。
                raise ValueError("Graph managed device is missing id")
            device = self.session.execute(
                select(Device).where(
                    Device.environment_id == self.environment_id,
                    Device.managed_tenant_id == self.managed_tenant_id,
                    Device.source_object_id == source_id,
                )
            ).scalar_one_or_none()
            if device is None:
                device = Device(
                    environment_id=self.environment_id,
                    managed_tenant_id=self.managed_tenant_id,
                    source_object_id=source_id,
                )
                self.session.add(device)
            # deviceName 少數情況可能為空（剛註冊未回報），退回 source id 以免破 NOT NULL。
            device.device_name = _clean(raw.get("deviceName")) or source_id
            device.operating_system = _clean(raw.get("operatingSystem"))
            device.os_version = _clean(raw.get("osVersion"))
            device.compliance_state = _clean(raw.get("complianceState"))
            device.owner_type = _clean(raw.get("managedDeviceOwnerType"))
            device.user_principal_name = _clean(raw.get("userPrincipalName"))
            device.serial_number = _clean(raw.get("serialNumber"))
            device.last_sync_time = _clean(raw.get("lastSyncDateTime"))
            device.last_seen_sync_id = self.sync_id
            processed += 1
        return processed

    def finalize_full_sync(self) -> int:
        result = self.session.execute(
            delete(Device).where(
                Device.environment_id == self.environment_id,
                Device.managed_tenant_id == self.managed_tenant_id,
                or_(Device.last_seen_sync_id.is_(None), Device.last_seen_sync_id != self.sync_id),
            )
        )
        return result.rowcount or 0


def seed_demo_devices(session: Session, *, environment_id, managed_tenant_id, count: int = 3) -> list[Device]:
    """僅供 manage.py seed-demo 使用；不透過 TenantContext（CLI 端已直接持有 environment_id）。"""
    created = []
    systems = ("Windows", "iOS", "Android")
    for i in range(1, count + 1):
        device = Device(
            environment_id=environment_id,
            managed_tenant_id=managed_tenant_id,
            source_object_id=f"demo-device-{i}",
            device_name=f"DEMO-PC-{i:02d}",
            operating_system=systems[(i - 1) % len(systems)],
            os_version="10.0.22631" if i % 2 else None,
            compliance_state="compliant" if i % 2 else "noncompliant",
            owner_type="company",
            user_principal_name=f"demo.user{i}@example.onmicrosoft.com" if i % 2 else None,
            serial_number=f"SN-{i:06d}" if i % 2 else None,
            last_sync_time="2026-07-11T00:00:00Z",
        )
        session.add(device)
        created.append(device)
    return created
