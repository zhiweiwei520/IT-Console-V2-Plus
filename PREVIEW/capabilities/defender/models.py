from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID,new_uuid
class DefenderAlert(db.Model):
    __tablename__="defender_alerts"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True)
    source_object_id=db.Column(db.String(128),nullable=False); title=db.Column(db.String(512),nullable=False); category=db.Column(db.String(128)); severity=db.Column(db.String(32)); status=db.Column(db.String(32))
    created_datetime=db.Column(db.DateTime,nullable=False); last_update_datetime=db.Column(db.DateTime); service_source=db.Column(db.String(128)); detection_source=db.Column(db.String(128)); description=db.Column(db.Text); alert_web_url=db.Column(db.String(1024))
    created_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False)
    __table_args__=(db.UniqueConstraint("managed_tenant_id","source_object_id",name="uq_defender_alert_tenant_source"),db.Index("ix_defender_alerts_tenant_created","managed_tenant_id","created_datetime"))
class DefenderSyncCheckpoint(db.Model):
    __tablename__="defender_sync_checkpoints"
    id=db.Column(GUID(),primary_key=True,default=new_uuid); job_id=db.Column(GUID(),db.ForeignKey("durable_jobs.id"),nullable=False,unique=True); environment_id=db.Column(GUID(),db.ForeignKey("management_environments.id"),nullable=False,index=True); managed_tenant_id=db.Column(GUID(),db.ForeignKey("managed_tenants.id"),nullable=False,index=True); window_start=db.Column(db.String(32)); next_resource=db.Column(db.String(2048)); processed_count=db.Column(db.Integer,nullable=False,default=0); status=db.Column(db.String(16),nullable=False,default="running"); started_at=db.Column(db.DateTime,default=utc_now_naive,nullable=False); updated_at=db.Column(db.DateTime,default=utc_now_naive,onupdate=utc_now_naive,nullable=False); completed_at=db.Column(db.DateTime)
