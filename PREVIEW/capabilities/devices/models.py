"""
devices capability — Intune 受管裝置（Microsoft Graph /deviceManagement/managedDevices）。

roadmap.md Phase B2：刻意選一個「形狀不同」的模組驗證 Graph 整合模式——
權限 scope 不同（DeviceManagementManagedDevices.Read.All，非 Directory 類）、資料量通常
大很多、且多數欄位可為空（未指派使用者、未回報序號的裝置），與 accounts「每欄位皆必填」
的形狀不同。沿用 accounts 垂直切片結構（models/repository/service/handler/routes/template）。
"""
from __future__ import annotations

from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)  # Intune managedDevice id
    device_name = db.Column(db.String(256), nullable=False)
    # 以下欄位 Intune 常見缺值（未指派使用者、未回報序號／OS 版本）：與 accounts 不同，一律 nullable。
    operating_system = db.Column(db.String(64), nullable=True)
    os_version = db.Column(db.String(64), nullable=True)
    compliance_state = db.Column(db.String(32), nullable=True)
    owner_type = db.Column(db.String(32), nullable=True)  # managedDeviceOwnerType: company/personal/unknown
    user_principal_name = db.Column(db.String(256), nullable=True)
    serial_number = db.Column(db.String(128), nullable=True)
    last_sync_time = db.Column(db.String(32), nullable=True)  # Graph lastSyncDateTime 原始 ISO 字串（顯示用）
    last_seen_sync_id = db.Column(GUID(), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_device_tenant_source_object"),
    )


class DeviceSyncCheckpoint(db.Model):
    """devices.sync page checkpoint；job 重送時從 next_resource 繼續（比照 AccountSyncCheckpoint）。"""
    __tablename__ = "device_sync_checkpoints"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(
        GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True,
    )
    managed_tenant_id = db.Column(
        GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True,
    )
    next_resource = db.Column(db.String(2048), nullable=True)
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="running")
    started_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False,
    )
    completed_at = db.Column(db.DateTime, nullable=True)
