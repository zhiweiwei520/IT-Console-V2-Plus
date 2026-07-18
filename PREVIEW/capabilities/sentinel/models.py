from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID,new_uuid
class SecurityIncident(db.Model):
    __tablename__="security_incidents"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True)
    source_object_id=db.Column(db.String(128),nullable=False); display_name=db.Column(db.String(512),nullable=False); severity=db.Column(db.String(32)); status=db.Column(db.String(32)); classification=db.Column(db.String(64)); determination=db.Column(db.String(64))
    created_datetime=db.Column(db.DateTime,nullable=False); last_update_datetime=db.Column(db.DateTime); assigned_to=db.Column(db.String(256)); incident_web_url=db.Column(db.String(1024))
    created_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False)
    __table_args__=(db.UniqueConstraint("managed_tenant_id","source_object_id",name="uq_security_incident_tenant_source"),db.Index("ix_security_incidents_tenant_created","managed_tenant_id","created_datetime"))
class SentinelSyncCheckpoint(db.Model):
    __tablename__="sentinel_sync_checkpoints"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); job_id=db.Column(GUID(),db.ForeignKey("durable_jobs.id"),nullable=False,unique=True); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True); window_start=db.Column(db.String(32)); next_resource=db.Column(db.String(2048)); processed_count=db.Column(db.Integer,nullable=False,default=0); status=db.Column(db.String(16),nullable=False,default="running"); started_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False); completed_at=db.Column(db.DateTime)
