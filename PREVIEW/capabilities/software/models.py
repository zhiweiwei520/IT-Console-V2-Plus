from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid

class DetectedSoftware(db.Model):
    __tablename__ = "detected_software"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(128), nullable=False)
    display_name = db.Column(db.String(256), nullable=False)
    version = db.Column(db.String(128))
    publisher = db.Column(db.String(256))
    platform = db.Column(db.String(64))
    size_in_bytes = db.Column(db.BigInteger)
    device_count = db.Column(db.Integer, nullable=False, default=0)
    last_seen_sync_id = db.Column(GUID(), index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    __table_args__ = (db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_detected_software_tenant_source"),)

class SoftwareSyncCheckpoint(db.Model):
    __tablename__ = "software_sync_checkpoints"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    next_resource = db.Column(db.String(2048))
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="running")
    started_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    completed_at = db.Column(db.DateTime)
