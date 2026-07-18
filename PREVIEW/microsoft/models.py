"""
app/microsoft/models.py
══════════════════════════════════════════════════════════════
受管 Entra Tenant 與連線。對應 03 §3 Data Plane 資料表草案（子集）。

刻意未實作（見 capability-manifest）：TenantCapability（capability scan 結果）、
真實 Key Vault 介接。BYO app 模式的 client secret 走 encrypted_client_secret 欄位
（Fernet 加密，見 app/microsoft/encryption.py），credential_ref 設為 `db:<connection_id>`
指回本表——這是 Key Vault 前的 dev/self-host 過渡方案，不是永久設計（見 capability-manifest）。
"""
from __future__ import annotations

from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class ManagedTenant(db.Model):
    """一個 Environment 管理的 Entra Tenant。"""
    __tablename__ = "managed_tenants"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    entra_tenant_id = db.Column(db.String(64), nullable=False)
    cloud = db.Column(db.String(16), nullable=False, default="public")  # D-11：MVP 僅 Azure Public
    display_name = db.Column(db.String(128), nullable=False)
    domain = db.Column(db.String(256), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="pending")
    # pending | active | degraded | revoked | disconnected（04 §4：與 onboarding operation state 分離）
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("environment_id", "entra_tenant_id", name="uq_managed_tenant_env_entra"),
    )

    def __repr__(self) -> str:
        return f"<ManagedTenant {self.display_name}>"


class TenantConnection(db.Model):
    """Graph 連線設定。credential 不進 DB 明文；MVP 僅存 reference 欄位骨架，未接 Key Vault。"""
    __tablename__ = "tenant_connections"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, unique=True)
    auth_mode = db.Column(db.String(16), nullable=False, default="provider_bundle")  # provider_bundle | byo_app
    client_id = db.Column(db.String(64), nullable=True)
    credential_ref = db.Column(db.String(256), nullable=True)  # "env:V2PLUS_*" 或 "db:<connection_id>"
    encrypted_client_secret = db.Column(db.Text, nullable=True)  # Fernet 密文；db: credential_ref 專用
    credential_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(16), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
