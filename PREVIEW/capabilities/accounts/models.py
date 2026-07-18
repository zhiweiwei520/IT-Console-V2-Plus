"""
accounts capability — 08-decision-log-and-backlog.md §5 spike 驗收指定的示範垂直切片。

本機 demo 仍可由 manage.py seed-demo 寫入；Phase 4 已提供 accounts.sync handler，待實際
GraphClient／Token Broker 接線後即可寫入真實 Entra 帳號資料。
"""
from __future__ import annotations

from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)  # Entra object id（stub）
    display_name = db.Column(db.String(128), nullable=False)
    user_principal_name = db.Column(db.String(256), nullable=False)
    account_enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_seen_sync_id = db.Column(GUID(), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_account_tenant_source_object"),
    )


class AccountSyncCheckpoint(db.Model):
    """accounts.sync page checkpoint；job 重送時從 next_resource 繼續。"""
    __tablename__ = "account_sync_checkpoints"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(
        GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True,
    )
    managed_tenant_id = db.Column(
        GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True,
    )
    next_resource = db.Column(db.String(2048), nullable=True)
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="running")
    started_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False,
    )
    completed_at = db.Column(db.DateTime, nullable=True)
