"""
signin_logs service。

與 accounts/devices 的關鍵差異（roadmap Phase B3 要驗證的「形狀」）：
- 增量 watermark：`watermark()` 取該 tenant 已同步的最新 createdDateTime，handler 據此只抓更新的資料。
- append-only：`upsert_page` 只 insert/update，**沒有 finalize_full_sync**（登入記錄是歷史事件，永不刪除）。
- 時間解析：Graph createdDateTime（ISO 8601、可能帶 Z 與 7 位小數）→ naive UTC 存 DB（CLAUDE.md B2）。
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.capabilities.signin_logs.models import SignInLog
from app.capabilities.signin_logs.repository import SignInLogRepository
from app.storage.tenant_context import TenantContext

_FRACTION = re.compile(r"\.(\d+)")


def parse_graph_datetime(value) -> datetime:
    """Graph ISO 8601（'2026-07-11T03:22:11Z' 或帶 7 位小數）→ naive UTC datetime。"""
    text = str(value or "").strip()
    if not text:
        raise ValueError("sign-in is missing createdDateTime")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    # fromisoformat 對小數位數的容忍度依 Python 版本而異；統一截到 6 位最保險。
    match = _FRACTION.search(text)
    if match:
        text = text[: match.start()] + "." + match.group(1)[:6] + text[match.end():]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"unparseable createdDateTime: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def to_graph_filter_iso(dt: datetime) -> str:
    """naive UTC datetime → Graph $filter 用的秒精度 ISO（配合 `ge` + 冪等 upsert 不漏邊界）。"""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class SignInLogService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.repository = SignInLogRepository(session, context)

    def list_recent(self, limit: int | None = None) -> list[SignInLog]:
        if not self.context.has_permission("signin_logs.view"):
            raise PermissionError("signin_logs.view required")
        if limit is None:
            return self.repository.list_recent()
        return self.repository.list_recent(limit=limit)


class SignInLogSyncService:
    """Worker 專用增量同步服務；scope 必須由已重驗證的 environment/tenant 顯式傳入。"""

    def __init__(self, session: Session, *, environment_id, managed_tenant_id, sync_id) -> None:
        self.session = session
        self.environment_id = environment_id
        self.managed_tenant_id = managed_tenant_id
        self.sync_id = sync_id

    def watermark(self) -> datetime | None:
        """該 tenant 已同步的最新 createdDateTime；None 代表尚未同步過（走初始視窗）。"""
        return self.session.execute(
            select(func.max(SignInLog.created_datetime)).where(
                SignInLog.environment_id == self.environment_id,
                SignInLog.managed_tenant_id == self.managed_tenant_id,
            )
        ).scalar_one_or_none()

    def upsert_page(self, sign_ins: list[dict]) -> int:
        processed = 0
        for raw in sign_ins:
            source_id = str(raw.get("id") or "").strip()
            if not source_id:
                raise ValueError("Graph sign-in is missing id")
            created = parse_graph_datetime(raw.get("createdDateTime"))
            row = self.session.execute(
                select(SignInLog).where(
                    SignInLog.environment_id == self.environment_id,
                    SignInLog.managed_tenant_id == self.managed_tenant_id,
                    SignInLog.source_object_id == source_id,
                )
            ).scalar_one_or_none()
            if row is None:
                row = SignInLog(
                    environment_id=self.environment_id,
                    managed_tenant_id=self.managed_tenant_id,
                    source_object_id=source_id,
                )
                self.session.add(row)
            row.created_datetime = created
            row.user_principal_name = _clean(raw.get("userPrincipalName"))
            row.user_display_name = _clean(raw.get("userDisplayName"))
            row.app_display_name = _clean(raw.get("appDisplayName"))
            row.ip_address = _clean(raw.get("ipAddress"))
            row.client_app_used = _clean(raw.get("clientAppUsed"))
            status_obj = raw.get("status") or {}
            error_code = status_obj.get("errorCode")
            if error_code is None:
                row.status = None
                row.failure_reason = None
            elif error_code == 0:
                row.status = "success"
                row.failure_reason = None
            else:
                row.status = "failure"
                row.failure_reason = _clean(status_obj.get("failureReason"))
            row.conditional_access_status = _clean(raw.get("conditionalAccessStatus"))
            processed += 1
        return processed

    # 刻意不提供 finalize_full_sync：登入記錄 append-only，同步只新增不刪除。


def _clean(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def seed_demo_sign_in_logs(session: Session, *, environment_id, managed_tenant_id, count: int = 4) -> list[SignInLog]:
    """僅供 manage.py seed-demo 使用；不透過 TenantContext（CLI 端已直接持有 environment_id）。"""
    created = []
    base = datetime(2026, 7, 11, 1, 0, 0)
    for i in range(1, count + 1):
        failed = i % 3 == 0
        row = SignInLog(
            environment_id=environment_id,
            managed_tenant_id=managed_tenant_id,
            source_object_id=f"demo-signin-{i}",
            created_datetime=base.replace(minute=i * 5),
            user_principal_name=f"demo.user{i}@example.onmicrosoft.com",
            user_display_name=f"Demo User {i}",
            app_display_name="Microsoft 365",
            ip_address=f"203.0.113.{i}",
            client_app_used="Browser",
            status="failure" if failed else "success",
            failure_reason="Invalid username or password." if failed else None,
            conditional_access_status="notApplied",
        )
        session.add(row)
        created.append(row)
    return created
