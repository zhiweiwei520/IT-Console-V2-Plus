"""
app/__init__.py
══════════════════════════════════════════════════════════════
V2+ console — Application Factory。

範圍（V2-P0 + V2-P2 spike，見 ../docs/capability-manifest.md）：
- 租戶核心（Principal / ManagementEnvironment / EnvironmentMembership / ManagedTenant）
- TenantContext + scoped repository + PostgreSQL RLS（09-development-standards.md）
- accounts capability 垂直切片（stub 資料，未接 Microsoft Graph）
- 本地登入（break-glass／environment-local）；Entra SSO 介面留待 D-02/D-03 定案與測試 Tenant 到位後接上

刻意不做（本次未實作，見 capability-manifest）：
- Deployment Stamp、Front Door／host resolver（MVP 用 session 式環境切換代替）
- Entra SSO（Admin Consent onboarding flow／使用者 SSO 登入callback）
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template

from config import get_config
from app.extensions import csrf, db, login_manager, migrate


def create_app(config_class=None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class or get_config())

    _ensure_secret_key(app)
    _ensure_directories(app)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    csrf.init_app(app)

    from app.platform.models import Principal
    from app.jobs import models as _job_models  # noqa: F401 — register migration metadata
    from app.storage.time_utils import to_taipei_str

    # 顯示層時區鐵則（CLAUDE.md B2）：模板一律 `| datetime_local` 轉 UTC+8，不直接 strftime。
    app.jinja_env.filters["datetime_local"] = to_taipei_str

    @login_manager.user_loader
    def load_principal(principal_id: str):
        return db.session.get(Principal, principal_id)

    from app.web.auth.routes import auth_bp
    from app.web.environments.routes import environments_bp
    from app.web.capabilities.accounts.routes import accounts_bp
    from app.web.capabilities.devices.routes import devices_bp
    from app.web.capabilities.signin_logs.routes import signin_logs_bp
    from app.web.capabilities.licenses.routes import licenses_bp
    from app.web.capabilities.app_audit.routes import app_audit_bp
    from app.web.capabilities.software.routes import software_bp
    from app.web.capabilities.teams.routes import teams_bp
    from app.web.capabilities.sharepoint.routes import sharepoint_bp
    from app.web.capabilities.defender.routes import defender_bp
    from app.web.capabilities.sentinel.routes import sentinel_bp
    from app.web.capabilities.dashboard.routes import dashboard_bp
    from app.capabilities.teams import models as _teams_models  # noqa: F401
    from app.capabilities.sharepoint import models as _sharepoint_models  # noqa: F401
    from app.capabilities.defender import models as _defender_models  # noqa: F401
    from app.capabilities.sentinel import models as _sentinel_models  # noqa: F401
    from app.capabilities.software import models as _software_models  # noqa: F401
    from app.capabilities.app_audit import models as _app_audit_models  # noqa: F401
    from app.capabilities.licenses import models as _license_models  # noqa: F401
    from app.web.platform.routes import platform_admin_bp
    from app.web.microsoft.routes import managed_tenants_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(environments_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(signin_logs_bp)
    app.register_blueprint(licenses_bp)
    app.register_blueprint(app_audit_bp)
    app.register_blueprint(software_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(sharepoint_bp)
    app.register_blueprint(defender_bp)
    app.register_blueprint(sentinel_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(platform_admin_bp)
    app.register_blueprint(managed_tenants_bp)

    @app.route("/")
    def index():
        from flask import redirect, url_for
        from flask_login import current_user
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return redirect(url_for("environments.list_environments"))

    @app.context_processor
    def _inject_navigation_state():
        import uuid
        from flask import session
        from flask_login import current_user
        from app.microsoft.models import ManagedTenant
        from app.platform.models import EnvironmentMembership, ManagementEnvironment
        from app.platform.permissions import is_platform_operator

        if not current_user.is_authenticated:
            return {
                "is_platform_operator": False,
                "nav_permissions": frozenset(),
                "nav_environment": None,
                "nav_tenant": None,
            }

        environment = None
        tenant = None
        permissions = frozenset()
        try:
            environment_id = uuid.UUID(session.get("active_environment_id", ""))
            environment = db.session.get(ManagementEnvironment, environment_id)
            membership = EnvironmentMembership.query.filter_by(
                environment_id=environment_id, principal_id=current_user.id, status="active",
            ).first()
            if environment is None or environment.status != "active" or membership is None:
                environment = None
            elif session.get("membership_version_seen") == membership.version:
                permissions = frozenset(membership.permission_codes)
                raw_tenant_id = session.get("active_managed_tenant_id")
                if raw_tenant_id:
                    tenant_id = uuid.UUID(raw_tenant_id)
                    if membership.all_managed_tenants or any(
                        grant.managed_tenant_id == tenant_id for grant in membership.tenant_grants
                    ):
                        tenant = ManagedTenant.query.filter_by(
                            id=tenant_id, environment_id=environment_id,
                        ).first()
                        if tenant is not None and tenant.status not in {"active", "degraded"}:
                            tenant = None
        except (ValueError, TypeError, AttributeError):
            environment = None
            tenant = None
            permissions = frozenset()

        return {
            "is_platform_operator": is_platform_operator(current_user.id),
            "nav_permissions": permissions,
            "nav_environment": environment,
            "nav_tenant": tenant,
        }

    @app.context_processor
    def _inject_sso_flag():
        # 供 login.html 決定是否顯示「使用 Entra 登入」；測試注入 broker 亦視為啟用。
        enabled = bool(app.config.get("ENTRA_SSO_ENABLED")) or (app.config.get("ENTRA_AUTH_BROKER") is not None)
        return {"entra_sso_enabled": enabled}

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    return app


def _ensure_secret_key(app: Flask) -> None:
    if app.config.get("SECRET_KEY"):
        return
    import secrets
    key_file: Path = app.config["INSTANCE_DIR"] / "secret.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
    else:
        key = secrets.token_hex(32)
        key_file.write_text(key, encoding="utf-8")
    app.config["SECRET_KEY"] = key


def _ensure_directories(app: Flask) -> None:
    app.config["INSTANCE_DIR"].mkdir(parents=True, exist_ok=True)
