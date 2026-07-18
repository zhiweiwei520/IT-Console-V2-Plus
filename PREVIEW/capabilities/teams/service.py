import json
from sqlalchemy import delete,or_,select
from app.capabilities.teams.models import TeamAudit
from app.capabilities.teams.repository import TeamsRepository
class TeamsService:
    def __init__(self,session,context): self.context,self.repository=context,TeamsRepository(session,context)
    def list_rows(self):
        if not self.context.has_permission("teams.view"): raise PermissionError("teams.view required")
        return self.repository.list_rows()
class TeamsSyncService:
    def __init__(self,session,*,environment_id,managed_tenant_id,sync_id): self.session,self.environment_id,self.managed_tenant_id,self.sync_id=session,environment_id,managed_tenant_id,sync_id
    def upsert(self,group,*,channels,members,owners,apps):
        source,name=str(group.get("id") or "").strip(),str(group.get("displayName") or "").strip()
        if not source or not name: raise ValueError("team group missing id or displayName")
        row=self.session.execute(select(TeamAudit).where(TeamAudit.environment_id==self.environment_id,TeamAudit.managed_tenant_id==self.managed_tenant_id,TeamAudit.source_object_id==source)).scalar_one_or_none()
        if row is None: row=TeamAudit(environment_id=self.environment_id,managed_tenant_id=self.managed_tenant_id,source_object_id=source); self.session.add(row)
        row.display_name=name; row.description=group.get("description"); row.visibility=group.get("visibility"); row.classification=group.get("classification"); row.created_datetime=group.get("createdDateTime"); row.is_archived=bool(group.get("isArchived")); row.channel_count=len(channels); row.member_count=len(members); row.owner_count=len(owners); row.guest_count=sum(1 for m in members if str(m.get("userType") or "").lower()=="guest"); row.installed_app_count=len(apps)
        row.channels_json=json.dumps(channels,ensure_ascii=False); row.members_json=json.dumps(members,ensure_ascii=False); row.engagement_json=json.dumps({"status":"not_collected","reason":"quick_sync"},ensure_ascii=False); row.security_json=json.dumps({"ownerless":not owners,"guestCount":row.guest_count,"installedApps":apps},ensure_ascii=False); row.last_seen_sync_id=self.sync_id
    def finalize(self): self.session.execute(delete(TeamAudit).where(TeamAudit.environment_id==self.environment_id,TeamAudit.managed_tenant_id==self.managed_tenant_id,or_(TeamAudit.last_seen_sync_id.is_(None),TeamAudit.last_seen_sync_id!=self.sync_id)))
