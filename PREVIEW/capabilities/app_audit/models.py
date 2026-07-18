from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid

class AppRegistration(db.Model):
    __tablename__ = "app_registrations"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)
    app_id = db.Column(db.String(64), nullable=False)
    display_name = db.Column(db.String(256), nullable=False)
    sign_in_audience = db.Column(db.String(64))
    publisher_domain = db.Column(db.String(256))
    credential_count = db.Column(db.Integer, nullable=False, default=0)
    nearest_credential_expiry = db.Column(db.String(64))
    last_seen_sync_id = db.Column(GUID(), index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    __table_args__ = (db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_app_registration_tenant_source"),)

class EnterpriseApp(db.Model):
    __tablename__ = "enterprise_apps"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)
    app_id = db.Column(db.String(64), nullable=False)
    display_name = db.Column(db.String(256), nullable=False)
    account_enabled = db.Column(db.Boolean)
    service_principal_type = db.Column(db.String(64))
    app_owner_organization_id = db.Column(db.String(64))
    last_seen_sync_id = db.Column(GUID(), index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    __table_args__ = (db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_enterprise_app_tenant_source"),)

class AppAuditCheckpoint(db.Model):
    __tablename__ = "app_audit_checkpoints"
    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    phase = db.Column(db.String(24), nullable=False, default="applications")
    next_resource = db.Column(db.String(2048))
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="running")
    started_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
    completed_at = db.Column(db.DateTime)
