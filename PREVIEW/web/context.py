"""
Web 殼層：解析 request/session，建構 TenantContext 後顯式傳給 service／repository（ADR-007 §4.3）。

本檔可以 import flask；app/storage/tenant_context.py、app/storage/repository.py、
app/capabilities/**/service.py 一律不行 —— 這是日後若要換殼（ASGI）唯一需要重寫的層。

解析順序（03 §6，MVP 版；host resolver 延後見 capability-manifest Δ3）：
  authenticated Principal → session 內 active_environment_id → Environment 狀態
  → active Membership → membership.version 與 session 快照比對 → Tenant Grant。
任何一步失敗即 401/403/404，不退回全域查詢。
"""
from __future__ import annotations

import uuid

from flask import abort, session
from flask_login import current_user

from app.extensions import db
from app.platform.models import EnvironmentMembership, ManagementEnvironment
from app.microsoft.models import ManagedTenant
from app.storage.rls import apply_rls_context
from app.storage.tenant_context import TenantContext


class NoActiveEnvironment(Exception):
    """尚未選擇 active environment；route 應導向 /environments。"""


class NoActiveTenant(Exception):
    """尚未選擇單一 Managed Tenant；route 應導向 Tenant 選擇頁。"""


def clear_active_tenant() -> None:
    session.pop("active_managed_tenant_id", None)


def _collect_tenant_grants(membership: EnvironmentMembership) -> frozenset[uuid.UUID] | None:
    if membership.all_managed_tenants:
        return None
    return frozenset(g.managed_tenant_id for g in membership.tenant_grants)


def require_tenant_context(
    required_permission: str | None = None, *, require_active_tenant: bool = False,
) -> TenantContext:
    """route 顯式呼叫；不做全域 before_request（09 §2：任何客戶資料 route 都必須顯式接收）。"""
    if not current_user.is_authenticated:
        abort(401)

    env_id_raw = session.get("active_environment_id")
    if not env_id_raw:
        clear_active_tenant()
        raise NoActiveEnvironment()

    try:
        env_id = uuid.UUID(env_id_raw)
    except (ValueError, TypeError, AttributeError):
        session.pop("active_environment_id", None)
        clear_active_tenant()
        raise NoActiveEnvironment()

    environment = db.session.get(ManagementEnvironment, env_id)
    if environment is None or environment.status != "active":
        session.pop("active_environment_id", None)
        clear_active_tenant()
        abort(404)

    membership = EnvironmentMembership.query.filter_by(
        environment_id=env_id, principal_id=current_user.id, status="active",
    ).first()
    if membership is None:
        session.pop("active_environment_id", None)
        clear_active_tenant()
        abort(404)

    if session.get("membership_version_seen") != membership.version:
        # membership 已被異動（suspend／revoke／改權限）；強制重新切換以取得最新授權（03 §9 60 秒失效目標）。
        session.pop("active_environment_id", None)
        session.pop("membership_version_seen", None)
        clear_active_tenant()
        abort(403)

    permission_codes = membership.permission_codes
    if required_permission and required_permission not in permission_codes:
        abort(403)

    active_tenant_raw = session.get("active_managed_tenant_id")
    active_tenant_id = None
    if active_tenant_raw:
        try:
            active_tenant_id = uuid.UUID(active_tenant_raw)
        except (ValueError, TypeError, AttributeError):
            clear_active_tenant()
            if require_active_tenant:
                raise NoActiveTenant()

    context = TenantContext(
        principal_id=current_user.id,
        environment_id=environment.id,
        membership_id=membership.id,
        allowed_managed_tenant_ids=_collect_tenant_grants(membership),
        active_managed_tenant_id=active_tenant_id,
        permission_codes=frozenset(permission_codes),
        correlation_id=str(uuid.uuid4()),
    )
    if active_tenant_id is not None and not context.can_access_tenant(active_tenant_id):
        clear_active_tenant()
        abort(403)
    if active_tenant_id is not None:
        tenant = ManagedTenant.query.filter_by(
            id=active_tenant_id, environment_id=environment.id,
        ).first()
        if tenant is None or tenant.status not in {"active", "degraded"}:
            clear_active_tenant()
            if require_active_tenant:
                raise NoActiveTenant()
            context = TenantContext(
                principal_id=context.principal_id,
                environment_id=context.environment_id,
                membership_id=context.membership_id,
                allowed_managed_tenant_ids=context.allowed_managed_tenant_ids,
                active_managed_tenant_id=None,
                permission_codes=context.permission_codes,
                correlation_id=context.correlation_id,
            )
    if require_active_tenant and context.active_managed_tenant_id is None:
        raise NoActiveTenant()

    apply_rls_context(db.session, context)
    return context
