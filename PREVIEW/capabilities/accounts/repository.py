from __future__ import annotations

from app.capabilities.accounts.models import Account
from app.storage.repository import TenantScopedRepository


class AccountRepository(TenantScopedRepository):
    model = Account

    def list_accounts(self):
        return self._base_query().order_by(Account.display_name.asc()).all()
