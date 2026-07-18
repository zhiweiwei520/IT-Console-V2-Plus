"""
平台管理者控制台：開設 Principal／Environment、指派 Membership／角色。

05-security-operations.md §3：platform_operator 只管生命週期，這裡的路由完全不查任何
Environment 業務資料（accounts 等），只操作 Control Plane 層的 Principal／Environment／
Membership schema。權限守門用 require_platform_operator()，不走 09 §5 的 environment
permission catalog（那是另一個維度，見 app/web/context.py）。
"""
from __future__ import annotations

import uuid

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.control_plane.service import add_membership, create_environment, create_principal
from app.extensions import db
from app.platform.models import EnvironmentMembership, EnvironmentRole, ManagementEnvironment, Principal
from app.platform.permissions import is_platform_operator
from app.web.platform.forms import EnvironmentForm, MembershipForm, PrincipalForm

platform_admin_bp = Blueprint("platform_admin", __name__, url_prefix="/platform")


def require_platform_operator() -> None:
    if not current_user.is_authenticated:
        abort(401)
    if not is_platform_operator(current_user.id):
        abort(403)


@platform_admin_bp.route("/")
@login_required
def dashboard():
    require_platform_operator()
    return redirect(url_for("platform_admin.list_environments"))


@platform_admin_bp.route("/principals")
@login_required
def list_principals():
    require_platform_operator()
    principals = Principal.query.order_by(Principal.created_at.desc()).all()
    return render_template("platform/principals/list.html", principals=principals)


@platform_admin_bp.route("/principals/new", methods=["GET", "POST"])
@login_required
def new_principal():
    require_platform_operator()
    form = PrincipalForm()
    if form.validate_on_submit():
        try:
            principal = create_principal(
                form.display_name.data,
                platform_username=form.platform_username.data or None,
                platform_password=form.platform_password.data or None,
                platform_operator=form.platform_operator.data,
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("platform/principals/new.html", form=form)
        flash(f"已建立使用者「{principal.display_name}」", "success")
        return redirect(url_for("platform_admin.list_principals"))
    return render_template("platform/principals/new.html", form=form)


@platform_admin_bp.route("/environments")
@login_required
def list_environments():
    require_platform_operator()
    environments = ManagementEnvironment.query.order_by(ManagementEnvironment.created_at.desc()).all()
    return render_template("platform/environments/list.html", environments=environments)


@platform_admin_bp.route("/environments/new", methods=["GET", "POST"])
@login_required
def new_environment():
    require_platform_operator()
    form = EnvironmentForm()
    if form.validate_on_submit():
        try:
            env = create_environment(form.slug.data, form.name.data)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("platform/environments/new.html", form=form)
        flash(f"已建立環境「{env.name}」", "success")
        return redirect(url_for("platform_admin.list_environments"))
    return render_template("platform/environments/new.html", form=form)


@platform_admin_bp.route("/environments/<uuid:environment_id>/memberships", methods=["GET", "POST"])
@login_required
def manage_memberships(environment_id: uuid.UUID):
    require_platform_operator()
    environment = db.get_or_404(ManagementEnvironment, environment_id)

    form = MembershipForm()
    form.principal_id.choices = [
        (str(p.id), p.display_name) for p in Principal.query.order_by(Principal.display_name).all()
    ]
    form.role_code.choices = [
        (r.code, r.label)
        for r in EnvironmentRole.query.filter_by(environment_id=environment.id).order_by(EnvironmentRole.code).all()
    ]

    if form.validate_on_submit():
        principal = db.get_or_404(Principal, uuid.UUID(form.principal_id.data))
        try:
            add_membership(
                environment, principal, role_code=form.role_code.data,
                all_managed_tenants=form.all_managed_tenants.data,
            )
        except ValueError as exc:
            flash(str(exc), "danger")
        else:
            flash(f"已將「{principal.display_name}」加入環境並指派角色", "success")
        return redirect(url_for("platform_admin.manage_memberships", environment_id=environment.id))

    memberships = (
        EnvironmentMembership.query
        .filter_by(environment_id=environment.id)
        .order_by(EnvironmentMembership.created_at.desc())
        .all()
    )
    return render_template(
        "platform/environments/memberships.html",
        environment=environment, memberships=memberships, form=form,
    )
