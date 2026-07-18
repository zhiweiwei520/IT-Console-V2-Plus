"""
app/platform/models.py
══════════════════════════════════════════════════════════════
租戶核心（Tenancy kernel）。對應 03-tenancy-identity-data.md §3 資料表草案。

命名紀律（09-development-standards.md §3）：
  environment_id  = ManagementEnvironment
  managed_tenant_id = ManagedTenant（見 app/microsoft/models.py）
  entra_tenant_id = 客戶 Entra Tenant 的外部 ID（存在 ManagedTenant，非本檔）
禁止用單一 tenant_id 同時代表兩種概念。

刻意未實作於此 spike（見 ../../docs/capability-manifest.md）：
  - principal_environment_index（Catalog／Stamp DB 未分離前，membership 表本身即為
    routing 查詢來源，此索引留到 Phase 5 Catalog 分離時再建）
  - Audit signing key／Blob anchor（hash chain 已實作）
"""
from __future__ import annotations

from flask_login import UserMixin
from sqlalchemy import event

from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class Principal(UserMixin, db.Model):
    """可登入平台的全域身分。Membership／角色／資料權限一律在 Environment 範圍，不在此表。"""
    __tablename__ = "principals"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    display_name = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="active")  # active | disabled
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    def get_id(self) -> str:  # Flask-Login 介面
        return str(self.id)

    @property
    def is_active(self) -> bool:  # 覆寫 UserMixin 預設 True
        return self.status == "active"

    def __repr__(self) -> str:
        return f"<Principal {self.display_name}>"


class ExternalLogin(db.Model):
    """Entra SSO 外部身分繫結。canonical key 固定 (canonical_issuer, subject)，禁止 email/UPN fallback。"""
    __tablename__ = "external_logins"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    principal_id = db.Column(GUID(), db.ForeignKey("principals.id"), nullable=False, index=True)
    canonical_issuer = db.Column(db.String(256), nullable=False)
    subject = db.Column(db.String(256), nullable=False)
    issuer_tenant_id = db.Column(db.String(64), nullable=True)
    object_id = db.Column(db.String(64), nullable=True)
    home_account_id = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("canonical_issuer", "subject", name="uq_external_login_issuer_subject"),
    )

    principal = db.relationship("Principal")


class PlatformLocalLogin(db.Model):
    """平台本地 break-glass 帳號（04/05 號文件：僅供 private endpoint／受控情境使用）。"""
    __tablename__ = "platform_local_logins"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    principal_id = db.Column(GUID(), db.ForeignKey("principals.id"), nullable=False, unique=True)
    normalized_username = db.Column(db.String(64), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    principal = db.relationship("Principal")

    def is_locked(self) -> bool:
        return bool(self.locked_until and utc_now_naive() < self.locked_until)


class PlatformRoleAssignment(db.Model):
    """僅 Control Plane／生命週期權限；不得隱含任何 Environment 資料存取（05-security-operations.md §3）。"""
    __tablename__ = "platform_role_assignments"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    principal_id = db.Column(GUID(), db.ForeignKey("principals.id"), nullable=False, index=True)
    role_code = db.Column(db.String(32), nullable=False)  # MVP 僅 "platform_operator"
    granted_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("principal_id", "role_code", name="uq_platform_role_principal_code"),
    )


class ManagementEnvironment(db.Model):
    """客戶的獨立管理環境；Environment 是資料、稽核、配額的第一隔離邊界。"""
    __tablename__ = "management_environments"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    slug = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="provisioning")
    # provisioning | active | suspended | offboarding | deleted
    isolation_mode = db.Column(db.String(16), nullable=False, default="pooled")
    membership_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    def __repr__(self) -> str:
        return f"<ManagementEnvironment {self.slug}>"


class Permission(db.Model):
    """全域權限目錄（dot notation，CLAUDE.md B4）。非 Environment 範圍資料，只是命名字典。"""
    __tablename__ = "permissions"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    code = db.Column(db.String(64), nullable=False, unique=True, index=True)
    label = db.Column(db.String(96), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="general")
    is_builtin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)


class EnvironmentRole(db.Model):
    """Environment 範圍角色（非平台角色）。"""
    __tablename__ = "environment_roles"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    code = db.Column(db.String(32), nullable=False)
    label = db.Column(db.String(64), nullable=False)
    is_builtin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("environment_id", "code", name="uq_environment_role_env_code"),
    )

    permissions = db.relationship(
        "Permission",
        secondary="role_permissions",
        backref=db.backref("environment_roles", lazy="dynamic"),
        lazy="joined",
    )

    def has_permission(self, code: str) -> bool:
        return any(p.code == code for p in self.permissions)


class RolePermission(db.Model):
    """environment_id 為冗餘欄位（來自 role.environment_id），讓本表也能直接套 RLS（09 §3：
    能用複合 FK／欄位防跨界關聯時必須使用），不必倚賴 join 才能限縮範圍。"""
    __tablename__ = "role_permissions"

    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    role_id = db.Column(GUID(), db.ForeignKey("environment_roles.id"), primary_key=True)
    permission_id = db.Column(GUID(), db.ForeignKey("permissions.id"), primary_key=True)
    granted_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)


class EnvironmentMembership(db.Model):
    """Principal 在 Environment 內的資格與狀態；Environment 授權真實來源。"""
    __tablename__ = "environment_memberships"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    principal_id = db.Column(GUID(), db.ForeignKey("principals.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="active")  # active | suspended
    all_managed_tenants = db.Column(db.Boolean, default=False, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("environment_id", "principal_id", name="uq_membership_env_principal"),
    )

    environment = db.relationship("ManagementEnvironment")
    principal = db.relationship("Principal")
    role_assignments = db.relationship("RoleAssignment", backref="membership", lazy="joined")
    tenant_grants = db.relationship("MembershipTenantGrant", backref="membership", lazy="joined")

    @property
    def permission_codes(self) -> set[str]:
        codes: set[str] = set()
        for ra in self.role_assignments:
            for p in ra.role.permissions:
                codes.add(p.code)
        return codes


class RoleAssignment(db.Model):
    """environment_id 冗餘自 membership，理由同 RolePermission。"""
    __tablename__ = "role_assignments"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    membership_id = db.Column(GUID(), db.ForeignKey("environment_memberships.id"), nullable=False, index=True)
    role_id = db.Column(GUID(), db.ForeignKey("environment_roles.id"), nullable=False, index=True)
    granted_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("membership_id", "role_id", name="uq_role_assignment_membership_role"),
    )

    role = db.relationship("EnvironmentRole")


class EnvironmentLocalLogin(db.Model):
    """D-03 若允許 Environment 本地帳號時使用；credential 不放在 Principal（03 §3）。"""
    __tablename__ = "environment_local_logins"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    principal_id = db.Column(GUID(), db.ForeignKey("principals.id"), nullable=False, index=True)
    normalized_username = db.Column(db.String(64), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("environment_id", "normalized_username", name="uq_env_local_login_username"),
        db.UniqueConstraint("environment_id", "principal_id", name="uq_env_local_login_principal"),
    )

    def is_locked(self) -> bool:
        return bool(self.locked_until and utc_now_naive() < self.locked_until)


class MembershipTenantGrant(db.Model):
    """Membership 可管理的 Managed Tenant 子集；all_managed_tenants=True 時本表不需列全部。
    environment_id 冗餘自 membership，理由同 RolePermission。"""
    __tablename__ = "membership_tenant_grants"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    membership_id = db.Column(GUID(), db.ForeignKey("environment_memberships.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("membership_id", "managed_tenant_id", name="uq_tenant_grant_membership_tenant"),
    )


class EnvironmentAuditLog(db.Model):
    """Append-only 稽核明細；每個 Environment 維護獨立 SHA-256 hash chain。"""
    __tablename__ = "environment_audit_logs"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    actor_principal_id = db.Column(GUID(), db.ForeignKey("principals.id"), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    target_type = db.Column(db.String(32), nullable=True)
    target_id = db.Column(db.String(64), nullable=True)
    outcome = db.Column(db.String(16), nullable=False, default="success")  # success | failure
    reason = db.Column(db.String(256), nullable=True)
    correlation_id = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False, index=True)
    chain_sequence = db.Column(db.BigInteger, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    entry_hash = db.Column(db.String(64), nullable=False)
    hash_version = db.Column(db.SmallInteger, nullable=False, default=1)

    __table_args__ = (
        db.UniqueConstraint(
            "environment_id", "chain_sequence", name="uq_audit_log_env_chain_sequence",
        ),
    )


class EnvironmentAuditChainHead(db.Model):
    """每個 Environment 的 audit chain head；寫入時於同一 transaction 更新。"""
    __tablename__ = "environment_audit_chain_heads"

    environment_id = db.Column(
        GUID(), db.ForeignKey("management_environments.id"), primary_key=True,
    )
    last_sequence = db.Column(db.BigInteger, nullable=False, default=0)
    last_hash = db.Column(db.String(64), nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False,
    )


@event.listens_for(EnvironmentAuditLog, "before_update")
def _block_audit_update(_mapper, _connection, _target) -> None:
    raise RuntimeError("EnvironmentAuditLog rows are append-only")


@event.listens_for(EnvironmentAuditLog, "before_delete")
def _block_audit_delete(_mapper, _connection, _target) -> None:
    raise RuntimeError("EnvironmentAuditLog rows are append-only")


@event.listens_for(EnvironmentAuditChainHead, "before_delete")
def _block_audit_head_delete(_mapper, _connection, _target) -> None:
    raise RuntimeError("EnvironmentAuditChainHead rows cannot be deleted")
