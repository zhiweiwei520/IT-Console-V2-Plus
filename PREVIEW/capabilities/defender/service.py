"""defender service — Microsoft Defender security alerts（Graph v1.0 /security/alerts_v2）。

roadmap Phase C6：第一個用 Security 類權限（`SecurityAlert.Read.All`）而非 Directory/Sites 類的
模組。形狀最接近 signin_logs——高頻時序、**watermark 增量**（依 createdDateTime 只抓更新的）、
**append-only 不刪除**（告警是歷史事件；狀態可變故重抓時 upsert 更新，不做 finalize 刪除）。
"""
from __future__ import annotations
from datetime import datetime,timezone
import re
from sqlalchemy import func,select
from app.capabilities.defender.models import DefenderAlert
from app.capabilities.defender.repository import DefenderRepository
_FRACTION=re.compile(r"\.(\d+)")
def parse_graph_datetime(value):
    """Graph ISO 8601（'2026-07-11T03:22:11Z' 或帶多位小數）→ naive UTC datetime（CLAUDE.md B2）。"""
    text=str(value or "").strip()
    if not text: raise ValueError("alert is missing createdDateTime")
    if text.endswith(("Z","z")): text=text[:-1]+"+00:00"
    match=_FRACTION.search(text)
    if match: text=text[:match.start()]+"."+match.group(1)[:6]+text[match.end():]
    try: parsed=datetime.fromisoformat(text)
    except ValueError as exc: raise ValueError(f"unparseable datetime: {value!r}") from exc
    if parsed.tzinfo is not None: parsed=parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
def to_graph_filter_iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
def _clean(value): text=str(value).strip() if value is not None else ""; return text or None
class DefenderService:
    def __init__(self,session,context): self.context,self.repository=context,DefenderRepository(session,context)
    def list_recent(self,limit=None):
        if not self.context.has_permission("defender.view"): raise PermissionError("defender.view required")
        return self.repository.list_recent() if limit is None else self.repository.list_recent(limit=limit)
class DefenderSyncService:
    def __init__(self,session,*,environment_id,managed_tenant_id,sync_id): self.session,self.environment_id,self.managed_tenant_id,self.sync_id=session,environment_id,managed_tenant_id,sync_id
    def watermark(self):
        """該 tenant 已同步告警的最新 createdDateTime；None 代表尚未同步過（走初始視窗）。"""
        return self.session.execute(select(func.max(DefenderAlert.created_datetime)).where(DefenderAlert.environment_id==self.environment_id,DefenderAlert.managed_tenant_id==self.managed_tenant_id)).scalar_one_or_none()
    def upsert_page(self,alerts):
        processed=0
        for raw in alerts:
            source=str(raw.get("id") or "").strip()
            if not source: raise ValueError("Graph alert is missing id")
            row=self.session.execute(select(DefenderAlert).where(DefenderAlert.environment_id==self.environment_id,DefenderAlert.managed_tenant_id==self.managed_tenant_id,DefenderAlert.source_object_id==source)).scalar_one_or_none()
            if row is None: row=DefenderAlert(environment_id=self.environment_id,managed_tenant_id=self.managed_tenant_id,source_object_id=source); self.session.add(row)
            last=raw.get("lastUpdateDateTime")
            row.title=_clean(raw.get("title")) or source; row.category=_clean(raw.get("category")); row.severity=_clean(raw.get("severity")); row.status=_clean(raw.get("status")); row.created_datetime=parse_graph_datetime(raw.get("createdDateTime")); row.last_update_datetime=parse_graph_datetime(last) if last else None
            row.service_source=_clean(raw.get("serviceSource")); row.detection_source=_clean(raw.get("detectionSource")); row.description=_clean(raw.get("description")); row.alert_web_url=_clean(raw.get("alertWebUrl")); processed+=1
        return processed
    # 刻意不提供 finalize：告警 append-only，同步只新增/更新不刪除。
