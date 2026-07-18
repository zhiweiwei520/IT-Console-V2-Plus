from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class LicenseSku(db.Model):
    __tablename__ = "license_skus"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)
    sku_part_number = db.Column(db.String(128), nullable=False)
    capability_status = db.Column(db.String(32))
    enabled_units = db.Column(db.Integer, nullable=False, default=0)
    consumed_units = db.Column(db.Integer, nullable=False, default=0)
    warning_units = db.Column(db.Integer, nullable=False, default=0)
    suspended_units = db.Column(db.Integer, nullable=False, default=0)
    last_seen_sync_id = db.Column(GUID(), index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    __table_args__ = (db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_license_sku_tenant_source"),)


class MfaRegistration(db.Model):
    __tablename__ = "mfa_registrations"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)
    user_principal_name = db.Column(db.String(256), nullable=False)
    user_display_name = db.Column(db.String(256))
    is_mfa_registered = db.Column(db.Boolean, nullable=False, default=False)
    is_mfa_capable = db.Column(db.Boolean, nullable=False, default=False)
    methods_registered = db.Column(db.String(512))
    last_seen_sync_id = db.Column(GUID(), index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    __table_args__ = (db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_mfa_registration_tenant_source"),)


class LicenseAuditCheckpoint(db.Model):
    __tablename__ = "license_audit_checkpoints"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    phase = db.Column(db.String(16), nullable=False, default="licenses")
    next_resource = db.Column(db.String(2048))
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="running")
    started_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    completed_at = db.Column(db.DateTime)
