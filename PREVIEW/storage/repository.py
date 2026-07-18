"""
Scoped repository 基底類別。

09-development-standards.md §2：
  「Repository 方法不得提供無 scope 的 all()／get(id)；使用 list_for_environment()、
   get_authorized() 等明確介面。」

這是 defense-in-depth 的第一層（獨立於 PostgreSQL RLS 第二層，見 app/storage/rls.py）；
SQLite 開發／單元測試環境沒有 RLS，本層是唯一防線，因此故意設計成「不提供任何繞過管道」。
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.storage.tenant_context import TenantContext


class ScopedRepository:
    """僅 environment_id 範圍的資源（例如 EnvironmentMembership、EnvironmentRole）。"""

    model: type = None  # 子類別必須覆寫

    def __init__(self, session: Session, context: TenantContext) -> None:
        if self.model is None:
            raise NotImplementedError("子類別必須設定 model")
        self.session = session
        self.context = context

    def _base_query(self):
        return self.session.query(self.model).filter(
            self.model.environment_id == self.context.environment_id
        )

    def list_for_environment(self, **equality_filters):
        q = self._base_query()
        for field_name, value in equality_filters.items():
            q = q.filter(getattr(self.model, field_name) == value)
        return q

    def get_authorized(self, record_id: uuid.UUID):
        """找不到或不在 scope 內一律回 None（呼叫端轉 404，不洩漏物件是否存在，見 09 §5）。"""
        return self._base_query().filter(self.model.id == record_id).first()


class TenantScopedRepository(ScopedRepository):
    """environment_id + managed_tenant_id 範圍的資源（Microsoft 快取／capability 資料）。"""

    def _authorized_tenant_ids(self) -> list[uuid.UUID] | None:
        """所有 capability 查詢必須鎖定單一 Tenant，禁止 Environment 內跨 Tenant 聚合。"""
        if self.context.active_managed_tenant_id is None:
            raise PermissionError("active_managed_tenant_id required")
        if not self.context.can_access_tenant(self.context.active_managed_tenant_id):
            raise PermissionError("active_managed_tenant_id not in grant")
        return [self.context.active_managed_tenant_id]

    def _base_query(self):
        q = super()._base_query()
        tenant_ids = self._authorized_tenant_ids()
        if tenant_ids is not None:
            q = q.filter(self.model.managed_tenant_id.in_(tenant_ids))
        return q
