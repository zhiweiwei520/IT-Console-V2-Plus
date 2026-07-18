from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID,new_uuid
class TeamAudit(db.Model):
    __tablename__="team_audits"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True)
    source_object_id=db.Column(db.String(64),nullable=False); display_name=db.Column(db.String(256),nullable=False); description=db.Column(db.Text); visibility=db.Column(db.String(32)); classification=db.Column(db.String(128)); created_datetime=db.Column(db.String(64)); is_archived=db.Column(db.Boolean,nullable=False,default=False)
    owner_count=db.Column(db.Integer,nullable=False,default=0); member_count=db.Column(db.Integer,nullable=False,default=0); guest_count=db.Column(db.Integer,nullable=False,default=0); channel_count=db.Column(db.Integer,nullable=False,default=0); installed_app_count=db.Column(db.Integer,nullable=False,default=0)
    channels_json=db.Column(db.Text,nullable=False,default="[]"); members_json=db.Column(db.Text,nullable=False,default="[]"); engagement_json=db.Column(db.Text,nullable=False,default="{}"); security_json=db.Column(db.Text,nullable=False,default="{}")
    last_seen_sync_id=db.Column(GUID(),index=True); created_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False)
    __table_args__=(db.UniqueConstraint("managed_tenant_id","source_object_id",name="uq_team_audit_tenant_source"),)
class TeamsSyncCheckpoint(db.Model):
    __tablename__="teams_sync_checkpoints"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); job_id=db.Column(GUID(),db.ForeignKey("durable_jobs.id"),nullable=False,unique=True); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True); next_resource=db.Column(db.String(2048)); processed_count=db.Column(db.Integer,nullable=False,default=0); status=db.Column(db.String(16),nullable=False,default="running"); started_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False); completed_at=db.Column(db.DateTime)
