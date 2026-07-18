import json
from sqlalchemy import delete,or_,select
from app.capabilities.sharepoint.models import SharePointSiteAudit
from app.capabilities.sharepoint.repository import SharePointRepository
def _storage(drives):
    for drive in drives:
        quota=drive.get("quota") if isinstance(drive,dict) else None
        if isinstance(quota,dict) and (quota.get("used") is not None or quota.get("total") is not None):
            used=quota.get("used"); total=quota.get("total")
            return (int(used) if used is not None else None,int(total) if total is not None else None)
    return (None,None)
class SharePointService:
    def __init__(self,session,context): self.context,self.repository=context,SharePointRepository(session,context)
    def list_rows(self):
        if not self.context.has_permission("sharepoint.view"): raise PermissionError("sharepoint.view required")
        return self.repository.list_rows()
class SharePointSyncService:
    def __init__(self,session,*,environment_id,managed_tenant_id,sync_id): self.session,self.environment_id,self.managed_tenant_id,self.sync_id=session,environment_id,managed_tenant_id,sync_id
    def upsert(self,site,*,drives):
        source,name=str(site.get("id") or "").strip(),str(site.get("displayName") or site.get("name") or "").strip()
        if not source or not name: raise ValueError("sharepoint site missing id or displayName")
        row=self.session.execute(select(SharePointSiteAudit).where(SharePointSiteAudit.environment_id==self.environment_id,SharePointSiteAudit.managed_tenant_id==self.managed_tenant_id,SharePointSiteAudit.source_object_id==source)).scalar_one_or_none()
        if row is None: row=SharePointSiteAudit(environment_id=self.environment_id,managed_tenant_id=self.managed_tenant_id,source_object_id=source); self.session.add(row)
        used,total=_storage(drives)
        row.display_name=name; row.web_url=site.get("webUrl"); row.description=site.get("description"); row.hostname=(site.get("siteCollection") or {}).get("hostname"); row.is_personal_site=bool(site.get("isPersonalSite")); row.created_datetime=site.get("createdDateTime"); row.last_modified_datetime=site.get("lastModifiedDateTime")
        row.library_count=len(drives); row.storage_used_bytes=used; row.storage_total_bytes=total; row.drives_json=json.dumps(drives,ensure_ascii=False); row.sharing_json=json.dumps({"status":"not_collected","reason":"quick_sync"},ensure_ascii=False); row.activity_json=json.dumps({"status":"not_collected","reason":"quick_sync"},ensure_ascii=False); row.last_seen_sync_id=self.sync_id
    def finalize(self): self.session.execute(delete(SharePointSiteAudit).where(SharePointSiteAudit.environment_id==self.environment_id,SharePointSiteAudit.managed_tenant_id==self.managed_tenant_id,or_(SharePointSiteAudit.last_seen_sync_id.is_(None),SharePointSiteAudit.last_seen_sync_id!=self.sync_id)))
