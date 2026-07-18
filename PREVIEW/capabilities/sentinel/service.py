"""sentinel service — Microsoft security incidents（Graph v1.0 /security/incidents）。

roadmap Phase C7（使用者拍板走 Graph incidents 而非真實 Log Analytics 查詢，避免動 token broker
resource allowlist 與新增 workspace 設定）。與 C6 defender 共用 client/token 基礎、形狀相同：
**watermark 增量**（依 createdDateTime 只抓更新的）、**append-only**（incidents 狀態可變故重抓時
upsert 更新，不做 finalize 刪除）。需 `SecurityIncident.Read.All`。
"""
from __future__ import annotations
from datetime import datetime,timezone
import re
from sqlalchemy import func,select
from app.capabilities.sentinel.models import SecurityIncident
from app.capabilities.sentinel.repository import SentinelRepository
_FRACTION=re.compile(r"\.(\d+)")
def parse_graph_datetime(value):
    """Graph ISO 8601（'2026-07-11T03:22:11Z' 或帶多位小數）→ naive UTC datetime（CLAUDE.md B2）。"""
    text=str(value or "").strip()
    if not text: raise ValueError("incident is missing createdDateTime")
    if text.endswith(("Z","z")): text=text[:-1]+"+00:00"
    match=_FRACTION.search(text)
    if match: text=text[:match.start()]+"."+match.group(1)[:6]+text[match.end():]
    try: parsed=datetime.fromisoformat(text)
    except ValueError as exc: raise ValueError(f"unparseable datetime: {value!r}") from exc
    if parsed.tzinfo is not None: parsed=parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
def to_graph_filter_iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
def _clean(value): text=str(value).strip() if value is not None else ""; return text or None
class SentinelService:
    def __init__(self,session,context): self.context,self.repository=context,SentinelRepository(session,context)
    def list_recent(self,limit=None):
        if not self.context.has_permission("sentinel.view"): raise PermissionError("sentinel.view required")
        return self.repository.list_recent() if limit is None else self.repository.list_recent(limit=limit)
class SentinelSyncService:
    def __init__(self,session,*,environment_id,managed_tenant_id,sync_id): self.session,self.environment_id,self.managed_tenant_id,self.sync_id=session,environment_id,managed_tenant_id,sync_id
    def watermark(self):
        """該 tenant 已同步 incidents 的最新 createdDateTime；None 代表尚未同步過（走初始視窗）。"""
        return self.session.execute(select(func.max(SecurityIncident.created_datetime)).where(SecurityIncident.environment_id==self.environment_id,SecurityIncident.managed_tenant_id==self.managed_tenant_id)).scalar_one_or_none()
    def upsert_page(self,incidents):
        processed=0
        for raw in incidents:
            source=str(raw.get("id") or "").strip()
            if not source: raise ValueError("Graph incident is missing id")
            row=self.session.execute(select(SecurityIncident).where(SecurityIncident.environment_id==self.environment_id,SecurityIncident.managed_tenant_id==self.managed_tenant_id,SecurityIncident.source_object_id==source)).scalar_one_or_none()
            if row is None: row=SecurityIncident(environment_id=self.environment_id,managed_tenant_id=self.managed_tenant_id,source_object_id=source); self.session.add(row)
            last=raw.get("lastUpdateDateTime")
            row.display_name=_clean(raw.get("displayName")) or source; row.severity=_clean(raw.get("severity")); row.status=_clean(raw.get("status")); row.classification=_clean(raw.get("classification")); row.determination=_clean(raw.get("determination")); row.created_datetime=parse_graph_datetime(raw.get("createdDateTime")); row.last_update_datetime=parse_graph_datetime(last) if last else None
            row.assigned_to=_clean(raw.get("assignedTo")); row.incident_web_url=_clean(raw.get("incidentWebUrl")); processed+=1
        return processed
    # 刻意不提供 finalize：incidents append-only，同步只新增/更新不刪除。
