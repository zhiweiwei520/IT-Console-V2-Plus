from flask import Blueprint,flash,redirect,render_template,url_for
from flask_login import login_required
from app.capabilities.sharepoint.service import SharePointService
from app.extensions import db
from app.jobs.dispatcher import SharePointSyncDispatcher
from app.web.context import NoActiveEnvironment,NoActiveTenant,require_tenant_context
sharepoint_bp=Blueprint("sharepoint",__name__,url_prefix="/capabilities/sharepoint")
@sharepoint_bp.route("/")
@login_required
def index():
    try: context=require_tenant_context("sharepoint.view",require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    return render_template("capabilities/sharepoint/list.html",context=context,rows=SharePointService(db.session,context).list_rows())
@sharepoint_bp.route("/sync",methods=["POST"])
@login_required
def sync():
    try: context=require_tenant_context("sharepoint.sync",require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    try: SharePointSyncDispatcher(db.session,context).enqueue(context.active_managed_tenant_id); db.session.commit(); flash("已排入 SharePoint 快速同步工作","success")
    except (PermissionError,ValueError) as exc: db.session.rollback(); flash(f"無法排入同步工作：{exc}","danger")
    return redirect(url_for("sharepoint.index"))
