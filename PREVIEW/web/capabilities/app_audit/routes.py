from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required
from app.capabilities.app_audit.service import AppAuditService
from app.extensions import db
from app.jobs.dispatcher import AppAuditSyncDispatcher
from app.web.context import NoActiveEnvironment, NoActiveTenant, require_tenant_context

app_audit_bp = Blueprint("app_audit", __name__, url_prefix="/capabilities/app-audit")
@app_audit_bp.route("/")
@login_required
def index():
    try: context = require_tenant_context("app_audit.view", require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    apps, enterprise_apps = AppAuditService(db.session, context).list_results()
    return render_template("capabilities/app_audit/list.html", context=context, apps=apps, enterprise_apps=enterprise_apps)
@app_audit_bp.route("/sync", methods=["POST"])
@login_required
def sync():
    try: context = require_tenant_context("app_audit.sync", require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    try: AppAuditSyncDispatcher(db.session, context).enqueue(context.active_managed_tenant_id); db.session.commit(); flash("已排入應用程式稽核同步工作", "success")
    except (PermissionError, ValueError) as exc: db.session.rollback(); flash(f"無法排入同步工作：{exc}", "danger")
    return redirect(url_for("app_audit.index"))
