from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID,new_uuid
class SharePointSiteAudit(db.Model):
    __tablename__="sharepoint_site_audits"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True)
    source_object_id=db.Column(db.String(255),nullable=False); display_name=db.Column(db.String(256),nullable=False); web_url=db.Column(db.String(1024)); description=db.Column(db.Text); hostname=db.Column(db.String(256)); is_personal_site=db.Column(db.Boolean,nullable=False,default=False)
    created_datetime=db.Column(db.String(64)); last_modified_datetime=db.Column(db.String(64)); library_count=db.Column(db.Integer,nullable=False,default=0); storage_used_bytes=db.Column(db.BigInteger); storage_total_bytes=db.Column(db.BigInteger)
    drives_json=db.Column(db.Text,nullable=False,default="[]"); sharing_json=db.Column(db.Text,nullable=False,default="{}"); activity_json=db.Column(db.Text,nullable=False,default="{}")
    last_seen_sync_id=db.Column(GUID(),index=True); created_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False)
    __table_args__=(db.UniqueConstraint("managed_tenant_id","source_object_id",name="uq_sharepoint_site_tenant_source"),)
class SharePointSyncCheckpoint(db.Model):
    __tablename__="sharepoint_sync_checkpoints"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); job_id=db.Column(GUID(),db.ForeignKey("durable_jobs.id"),nullable=False,unique=True); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True); next_resource=db.Column(db.String(2048)); processed_count=db.Column(db.Integer,nullable=False,default=0); status=db.Column(db.String(16),nullable=False,default="running"); started_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False); completed_at=db.Column(db.DateTime)
