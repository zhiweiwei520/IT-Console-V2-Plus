from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.capabilities.licenses.service import LicenseAuditService
from app.extensions import db
from app.jobs.dispatcher import LicenseAuditSyncDispatcher
from app.web.context import NoActiveEnvironment, NoActiveTenant, require_tenant_context

licenses_bp = Blueprint("licenses", __name__, url_prefix="/capabilities/licenses")

@licenses_bp.route("/")
@login_required
def list_licenses():
    try:
        context = require_tenant_context("licenses.view", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        return redirect(url_for("managed_tenants.list_managed_tenants"))
    skus, users = LicenseAuditService(db.session, context).list_results()
    return render_template("capabilities/licenses/list.html", context=context, skus=skus, users=users)

@licenses_bp.route("/sync", methods=["POST"])
@login_required
def sync_licenses():
    try:
        context = require_tenant_context("licenses.sync", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        return redirect(url_for("managed_tenants.list_managed_tenants"))
    try:
        LicenseAuditSyncDispatcher(db.session, context).enqueue(context.active_managed_tenant_id)
        db.session.commit()
    except (PermissionError, ValueError) as exc:
        db.session.rollback()
        flash(f"無法排入同步工作：{exc}", "danger")
        return redirect(url_for("licenses.list_licenses"))
    flash("已排入授權與 MFA 稽核同步工作", "success")
    return redirect(url_for("licenses.list_licenses"))
