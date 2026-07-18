"""
Managed Tenant 連接管理（BYO app 自助輸入版，見 app/microsoft/onboarding_service.py 說明）。

route 只做「解析 request → 呼叫 service → 組 response」的薄殼（ADR-007 §4.3）；
建立與測試連線的邏輯都在 onboarding_service.py，這裡不重複寫驗證規則。
"""
from __future__ import annotations

import asyncio
import uuid

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for
from flask_login import login_required

from app.extensions import db
from app.microsoft.models import ManagedTenant, TenantConnection
from app.microsoft.onboarding_service import (
    apply_connection_test_result,
    create_byo_managed_tenant,
    test_tenant_connection,
)
from app.platform.audit import record_audit
from app.web.context import NoActiveEnvironment, require_tenant_context
from app.web.microsoft.forms import ManagedTenantForm

managed_tenants_bp = Blueprint("managed_tenants", __name__, url_prefix="/microsoft/managed-tenants")

TENANT_ACCESS_PERMISSIONS = frozenset({
    "environment.tenants.manage",
    "accounts.view", "accounts.sync",
    "devices.view", "devices.sync",
    "signin_logs.view", "signin_logs.sync",
    "licenses.view", "licenses.sync",
    "app_audit.view", "app_audit.sync",
    "software.view", "software.sync",
    "teams.view", "teams.sync",
})


def _can_select_tenant(context) -> bool:
    return bool(context.permission_codes & TENANT_ACCESS_PERMISSIONS)


@managed_tenants_bp.route("/")
@login_required
def list_managed_tenants():
    try:
        context = require_tenant_context()
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    if not _can_select_tenant(context):
        abort(403)

    query = ManagedTenant.query.filter_by(environment_id=context.environment_id)
    if context.allowed_managed_tenant_ids is not None:
        query = query.filter(ManagedTenant.id.in_(context.allowed_managed_tenant_ids))
    tenants = query.order_by(ManagedTenant.created_at.desc()).all()
    return render_template("microsoft/managed_tenants/list.html", tenants=tenants, context=context)


@managed_tenants_bp.route("/<uuid:tenant_id>/switch", methods=["POST"])
@login_required
def switch_managed_tenant(tenant_id: uuid.UUID):
    try:
        context = require_tenant_context()
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    if not _can_select_tenant(context):
        abort(403)

    tenant = ManagedTenant.query.filter_by(
        id=tenant_id, environment_id=context.environment_id,
    ).first_or_404()
    if not context.can_access_tenant(tenant.id):
        abort(404)
    if tenant.status not in {"active", "degraded"}:
        flash("此 Tenant 尚未通過連線驗證，無法進入管理", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    session["active_managed_tenant_id"] = str(tenant.id)
    record_audit(
        environment_id=context.environment_id, actor_principal_id=context.principal_id,
        action="managed_tenant.switch", target_type="managed_tenant", target_id=tenant.id,
        correlation_id=context.correlation_id,
    )
    db.session.commit()
    flash(f"目前管理 Tenant 已切換為「{tenant.display_name}」", "success")
    for permission, endpoint in (
        ("accounts.view", "accounts.list_accounts"),
        ("devices.view", "devices.list_devices"),
        ("signin_logs.view", "signin_logs.list_sign_ins"),
    ):
        if context.has_permission(permission):
            return redirect(url_for(endpoint))
    return redirect(url_for("managed_tenants.list_managed_tenants"))


@managed_tenants_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_managed_tenant():
    try:
        context = require_tenant_context("environment.tenants.manage")
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))

    form = ManagedTenantForm()
    if form.validate_on_submit():
        try:
            tenant = create_byo_managed_tenant(
                context.environment_id,
                entra_tenant_id=form.entra_tenant_id.data,
                display_name=form.display_name.data,
                domain=form.domain.data,
                client_id=form.client_id.data,
                client_secret=form.client_secret.data,
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("microsoft/managed_tenants/new.html", form=form)

        record_audit(
            environment_id=context.environment_id, actor_principal_id=context.principal_id,
            action="managed_tenant.create", target_type="managed_tenant", target_id=tenant.id,
            correlation_id=context.correlation_id,
        )
        db.session.commit()
        flash(f"已新增 Managed Tenant「{tenant.display_name}」，狀態為 pending，請按「測試連線」確認憑證正確", "success")
        return redirect(url_for("managed_tenants.list_managed_tenants"))
    return render_template("microsoft/managed_tenants/new.html", form=form)


@managed_tenants_bp.route("/<uuid:tenant_id>/test-connection", methods=["POST"])
@login_required
def test_connection(tenant_id: uuid.UUID):
    try:
        context = require_tenant_context("environment.tenants.manage")
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))

    tenant = ManagedTenant.query.filter_by(
        id=tenant_id, environment_id=context.environment_id,
    ).first_or_404()
    connection = TenantConnection.query.filter_by(
        environment_id=context.environment_id, managed_tenant_id=tenant.id,
    ).first()
    if connection is None:
        flash("此 Managed Tenant 沒有連線設定", "danger")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    result = asyncio.run(test_tenant_connection(context.environment_id, tenant.id))

    try:
        apply_connection_test_result(tenant, connection, result)
    except ValueError as exc:
        record_audit(
            environment_id=context.environment_id, actor_principal_id=context.principal_id,
            action="managed_tenant.test_connection", target_type="managed_tenant", target_id=tenant.id,
            outcome="failure", reason=str(exc), correlation_id=context.correlation_id,
        )
        db.session.commit()
        flash(str(exc), "danger")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    record_audit(
        environment_id=context.environment_id, actor_principal_id=context.principal_id,
        action="managed_tenant.test_connection", target_type="managed_tenant", target_id=tenant.id,
        outcome="success" if result.success else "failure", reason=result.error,
        correlation_id=context.correlation_id,
    )
    db.session.commit()

    if result.success:
        flash(f"連線成功：{result.remote_display_name or tenant.display_name}", "success")
    else:
        flash(f"連線失敗：{result.error}", "danger")
    return redirect(url_for("managed_tenants.list_managed_tenants"))
