from flask import Blueprint,redirect,render_template,url_for
from flask_login import login_required
from app.capabilities.dashboard.service import DashboardService
from app.extensions import db
from app.web.context import NoActiveEnvironment,NoActiveTenant,require_tenant_context
dashboard_bp=Blueprint("dashboard",__name__,url_prefix="/dashboard")
@dashboard_bp.route("/")
@login_required
def index():
    # required_permission=None：任何環境成員皆可進入；各 KPI 由 service 依權限個別 gate（Issue #5）。
    try: context=require_tenant_context(require_active_tenant=True)
    except NoActiveEnvironment: return redirect(url_for("environments.list_environments"))
    except NoActiveTenant: return redirect(url_for("managed_tenants.list_managed_tenants"))
    return render_template("capabilities/dashboard/index.html",context=context,kpis=DashboardService(db.session,context).kpis())
