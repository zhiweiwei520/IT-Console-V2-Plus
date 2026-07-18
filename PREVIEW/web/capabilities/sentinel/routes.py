from flask import Blueprint,flash,redirect,render_template,url_for
from flask_login import login_required
from app.capabilities.sentinel.service import SentinelService
from app.extensions import db
from app.jobs.dispatcher import SentinelSyncDispatcher
from app.web.context import NoActiveEnvironment,NoActiveTenant,require_tenant_context
sentinel_bp=Blueprint("sentinel",__name__,url_prefix="/capabilities/sentinel")
@sentinel_bp.route("/")
@login_required
def index():
    try: context=require_tenant_context("sentinel.view",require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    return render_template("capabilities/sentinel/list.html",context=context,rows=SentinelService(db.session,context).list_recent())
@sentinel_bp.route("/sync",methods=["POST"])
@login_required
def sync():
    try: context=require_tenant_context("sentinel.sync",require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    try: SentinelSyncDispatcher(db.session,context).enqueue(context.active_managed_tenant_id); db.session.commit(); flash("已排入資安事件增量同步工作","success")
    except (PermissionError,ValueError) as exc: db.session.rollback(); flash(f"無法排入同步工作：{exc}","danger")
    return redirect(url_for("sentinel.index"))
