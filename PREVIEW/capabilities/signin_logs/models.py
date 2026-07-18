"""
signin_logs capability — Entra 登入記錄（Microsoft Graph /auditLogs/signIns）。

roadmap.md Phase B3：第三個「形狀不同」的模組，刻意與 accounts/devices 的「全量同步 + 刪除
過期」相反——登入記錄是 append-only 高頻事件，改用 **watermark 增量**（依 createdDateTime
時間篩選只抓比上次更新的資料），且**永不刪除既有資料**（沒有 last_seen_sync_id、沒有
finalize_full_sync）。這正是要驗證「模組開發模板」不能對 full-sync 過度擬合的關鍵案例。
需 `AuditLog.Read.All` 權限。
"""
from __future__ import annotations

from app.extensions import db
from app.storage.time_utils import utc_now_naive
from app.storage.types import GUID, new_uuid


class SignInLog(db.Model):
    __tablename__ = "sign_in_logs"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    environment_id = db.Column(GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True)
    managed_tenant_id = db.Column(GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True)
    source_object_id = db.Column(db.String(64), nullable=False)  # Graph signIn id
    # 事件發生時間（naive UTC，CLAUDE.md B2）：watermark 增量的比較欄位，顯示層另轉 UTC+8。
    created_datetime = db.Column(db.DateTime, nullable=False)
    user_principal_name = db.Column(db.String(256), nullable=True)
    user_display_name = db.Column(db.String(256), nullable=True)
    app_display_name = db.Column(db.String(256), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    client_app_used = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(16), nullable=True)  # success / failure（由 status.errorCode 推導）
    failure_reason = db.Column(db.String(256), nullable=True)
    conditional_access_status = db.Column(db.String(32), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("managed_tenant_id", "source_object_id", name="uq_signin_tenant_source_object"),
        # watermark 查詢 MAX(created_datetime) per tenant，複合索引避免全表掃描。
        db.Index("ix_sign_in_logs_tenant_created", "managed_tenant_id", "created_datetime"),
    )


class SignInLogSyncCheckpoint(db.Model):
    """signin_logs.sync page checkpoint。

    與 accounts/devices 的差異：多一個 window_start——記錄本次增量查詢的時間下界（watermark），
    resume 時用它重建 $filter（而非重新計算 watermark，否則跨頁邊界會漂移）。
    """
    __tablename__ = "sign_in_log_sync_checkpoints"

    id = db.Column(GUID(), primary_key=True, default=new_uuid)
    job_id = db.Column(GUID(), db.ForeignKey("durable_jobs.id"), nullable=False, unique=True)
    environment_id = db.Column(
        GUID(), db.ForeignKey("management_environments.id"), nullable=False, index=True,
    )
    managed_tenant_id = db.Column(
        GUID(), db.ForeignKey("managed_tenants.id"), nullable=False, index=True,
    )
    window_start = db.Column(db.String(32), nullable=True)  # 本次增量的 createdDateTime 下界（ISO）
    next_resource = db.Column(db.String(2048), nullable=True)
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default="running")
    started_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False,
    )
    completed_at = db.Column(db.DateTime, nullable=True)
