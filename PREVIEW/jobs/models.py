"""Durable PostgreSQL queue persistence models（Phase 4 MVP）。"""
from __future__ import annotations

from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class DurableJob(db.Model):
    __tablename__ = "durable_jobs"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(
        GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True,
    )
    managed_tenant_id = db.Column(
        GUID(), db.ForeignKey("managed_tenants.id"), nullable=True, index=True,
    )
    execution_id = db.Column(GUID(), nullable=True, index=True)
    schema_version = db.Column(db.SmallInteger, nullable=False, default=1)
    job_type = db.Column(db.String(64), nullable=False, index=True)
    job_version = db.Column(db.SmallInteger, nullable=False, default=1)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    idempotency_key = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="queued", index=True)
    attempt = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    available_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, index=True)
    lease_owner = db.Column(db.String(128), nullable=True)
    lease_expires_at = db.Column(db.DateTime, nullable=True, index=True)
    trace_id = db.Column(db.String(64), nullable=True)
    last_error = db.Column(db.String(512), nullable=True)
    requested_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "environment_id", "idempotency_key", name="uq_durable_job_env_idempotency",
        ),
        db.Index(
            "ix_durable_jobs_env_claim",
            "environment_id", "status", "available_at", "lease_expires_at",
        ),
    )


class JobDeadLetter(db.Model):
    __tablename__ = "job_dead_letters"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(
        GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True,
    )
    managed_tenant_id = db.Column(
        GUID(), db.ForeignKey("managed_tenants.id"), nullable=True, index=True,
    )
    job_type = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    attempts = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(512), nullable=False)
    dead_lettered_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

