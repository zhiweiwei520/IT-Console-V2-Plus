"""
環境列表與切換。刻意只查詢 current_user 實際擁有的 EnvironmentMembership——
即使是 platform_operator 也不隱含任何 Environment 存取（05-security-operations.md §3：
「禁止 platform_operator 隱含所有 Environment permission」），所以這裡不做任何
「平台角色可看全部環境」的特例。
"""
from __future__ import annotations

import uuid

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required

from app.platform.models import EnvironmentMembership, ManagementEnvironment

environments_bp = Blueprint("environments", __name__, url_prefix="/environments")


@environments_bp.route("/")
@login_required
def list_environments():
    memberships = (
        EnvironmentMembership.query
        .filter_by(principal_id=current_user.id, status="active")
        .join(ManagementEnvironment)
        .filter(ManagementEnvironment.status == "active")
        .all()
    )
    active_id = session.get("active_environment_id")
    return render_template("environments/list.html", memberships=memberships, active_id=active_id)


@environments_bp.route("/<uuid:environment_id>/switch", methods=["POST"])
@login_required
def switch_environment(environment_id: uuid.UUID):
    membership = EnvironmentMembership.query.filter_by(
        environment_id=environment_id, principal_id=current_user.id, status="active",
    ).first()
    if membership is None:
        abort(404)
    environment = membership.environment
    if environment.status != "active":
        abort(404)
    session["active_environment_id"] = str(environment.id)
    session["membership_version_seen"] = membership.version
    session.pop("active_managed_tenant_id", None)
    flash(f"已切換至環境「{environment.name}」", "success")
    return redirect(url_for("managed_tenants.list_managed_tenants"))
