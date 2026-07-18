"""
accounts service。

Web 查詢 service、Worker page upsert service，以及 manage.py demo seed helper。
Graph I/O 位於 handler.py，透過 app/microsoft/graph_client.py protocol 注入。
"""
from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.capabilities.accounts.models import Account
from app.capabilities.accounts.repository import AccountRepository
from app.storage.tenant_context import TenantContext


class AccountService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.repository = AccountRepository(session, context)

    def list_accounts(self) -> list[Account]:
        if not self.context.has_permission("accounts.view"):
            raise PermissionError("accounts.view required")
        return self.repository.list_accounts()


class AccountSyncService:
    """Worker 專用同步服務；scope 必須由已重驗證的 environment/tenant 顯式傳入。"""

    def __init__(self, session: Session, *, environment_id, managed_tenant_id, sync_id) -> None:
        self.session = session
        self.environment_id = environment_id
        self.managed_tenant_id = managed_tenant_id
        self.sync_id = sync_id

    def upsert_page(self, users: list[dict]) -> int:
        processed = 0
        for user in users:
            source_id = str(user.get("id") or "").strip()
            display_name = str(user.get("displayName") or "").strip()
            upn = str(user.get("userPrincipalName") or "").strip()
            if not source_id or not display_name or not upn:
                raise ValueError("Graph user is missing id, displayName or userPrincipalName")
            account = self.session.execute(
                select(Account).where(
                    Account.environment_id == self.environment_id,
                    Account.managed_tenant_id == self.managed_tenant_id,
                    Account.source_object_id == source_id,
                )
            ).scalar_one_or_none()
            if account is None:
                account = Account(
                    environment_id=self.environment_id,
                    managed_tenant_id=self.managed_tenant_id,
                    source_object_id=source_id,
                )
                self.session.add(account)
            account.display_name = display_name
            account.user_principal_name = upn
            account.account_enabled = bool(user.get("accountEnabled", True))
            account.last_seen_sync_id = self.sync_id
            processed += 1
        return processed

    def finalize_full_sync(self) -> int:
        result = self.session.execute(
            delete(Account).where(
                Account.environment_id == self.environment_id,
                Account.managed_tenant_id == self.managed_tenant_id,
                or_(Account.last_seen_sync_id.is_(None), Account.last_seen_sync_id != self.sync_id),
            )
        )
        return result.rowcount or 0


def seed_demo_accounts(session: Session, *, environment_id, managed_tenant_id, count: int = 3) -> list[Account]:
    """僅供 manage.py seed-demo 使用；不透過 TenantContext（CLI 端已直接持有 environment_id）。"""
    created = []
    for i in range(1, count + 1):
        account = Account(
            environment_id=environment_id,
            managed_tenant_id=managed_tenant_id,
            source_object_id=f"demo-object-{i}",
            display_name=f"Demo User {i}",
            user_principal_name=f"demo.user{i}@example.onmicrosoft.com",
            account_enabled=True,
        )
        session.add(account)
        created.append(account)
    return created
