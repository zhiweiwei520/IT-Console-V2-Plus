from __future__ import annotations

from app.capabilities.signin_logs.models import SignInLog
from app.storage.repository import TenantScopedRepository

# 高頻資料：清單頁預設只取最近 N 筆（資料量控制，roadmap Phase B3）。
DEFAULT_LIST_LIMIT = 200


class SignInLogRepository(TenantScopedRepository):
    model = SignInLog

    def list_recent(self, limit: int = DEFAULT_LIST_LIMIT):
        return (
            self._base_query()
            .order_by(SignInLog.created_datetime.desc())
            .limit(limit)
            .all()
        )
