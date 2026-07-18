"""
PostgreSQL RLS session context helper。

03-tenancy-identity-data.md §7：transaction 開始後以參數化 set_config(..., true) 設定
transaction-local app.environment_id / app.principal_id / app.managed_tenant_id。
SQLite（dev／單元測試）無 RLS 語法，此處為 no-op —— 該情境下唯一防線是
app/storage/repository.py 的 scoped repository（09 §2）。
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.storage.tenant_context import TenantContext


def apply_rls_context(session: Session, context: TenantContext) -> None:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT set_config('app.environment_id', :v, true)"),
        {"v": str(context.environment_id)},
    )
    session.execute(
        text("SELECT set_config('app.principal_id', :v, true)"),
        {"v": str(context.principal_id)},
    )
    session.execute(
        text("SELECT set_config('app.managed_tenant_id', :v, true)"),
        {"v": str(context.active_managed_tenant_id) if context.active_managed_tenant_id else ""},
    )


def clear_rls_context(session: Session) -> None:
    """Connection pool checkout／checkin 之間必須清空，避免殘留前一個 tenant setting（07 §3）。"""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for key in ("app.environment_id", "app.principal_id", "app.managed_tenant_id"):
        session.execute(text("SELECT set_config(:k, '', true)"), {"k": key})
