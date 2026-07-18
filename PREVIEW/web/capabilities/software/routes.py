from flask import Blueprint,flash,redirect,render_template,url_for
from flask_login import login_required
from app.capabilities.software.service import SoftwareService
from app.extensions import db
from app.jobs.dispatcher import SoftwareSyncDispatcher
from app.web.context import NoActiveEnvironment,NoActiveTenant,require_tenant_context
software_bp=Blueprint("software",__name__,url_prefix="/capabilities/software")
@software_bp.route("/")
@login_required
def index():
    try: context=require_tenant_context("software.view",require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    return render_template("capabilities/software/list.html",context=context,rows=SoftwareService(db.session,context).list_rows())
@software_bp.route("/sync",methods=["POST"])
@login_required
def sync():
    try: context=require_tenant_context("software.sync",require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    try: SoftwareSyncDispatcher(db.session,context).enqueue(context.active_managed_tenant_id); db.session.commit(); flash("已排入軟體清冊同步工作","success")
    except (PermissionError,ValueError) as exc: db.session.rollback(); flash(f"無法排入同步工作：{exc}","danger")
    return redirect(url_for("software.index"))
