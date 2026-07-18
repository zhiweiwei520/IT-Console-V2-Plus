"""
TenantContext — 03-tenancy-identity-data.md §6 / 09-development-standards.md §2 邊界規則。

框架無關（ADR-007 §4.3）：此檔案禁止 import flask。由 web 殼層（app/web/context.py）解析
request 後建構，再顯式傳給 service／repository／Worker handler；service／repository／jobs
層一律不得從 flask.g、flask.session 或任意 header 自行取得 Environment。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TenantContext:
    principal_id: uuid.UUID
    environment_id: uuid.UUID
    membership_id: uuid.UUID
    permission_codes: frozenset[str]
    correlation_id: str
    # None = 具 all_managed_tenants 授權（可查該 Environment 全部 Managed Tenant）
    # frozenset(...) = 明確 Tenant grant 子集
    allowed_managed_tenant_ids: frozenset[uuid.UUID] | None = None
    # 目前操作鎖定的單一 Managed Tenant（例如列表頁篩選、Worker execution 綁定）
    active_managed_tenant_id: uuid.UUID | None = None

    def has_permission(self, code: str) -> bool:
        return code in self.permission_codes

    def can_access_tenant(self, managed_tenant_id: uuid.UUID) -> bool:
        if self.allowed_managed_tenant_ids is None:
            return True  # all-tenant grant
        return managed_tenant_id in self.allowed_managed_tenant_ids

    def narrowed_to_tenant(self, managed_tenant_id: uuid.UUID) -> "TenantContext":
        """回傳鎖定單一 Managed Tenant 的新 context（Worker execution 應使用此變體）。"""
        if not self.can_access_tenant(managed_tenant_id):
            raise PermissionError(f"managed_tenant {managed_tenant_id} not in grant")
        return replace(self, active_managed_tenant_id=managed_tenant_id)
