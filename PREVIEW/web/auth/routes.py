"""
本地登入（break-glass／environment-local）。

⚠️ Entra SSO 未實作（見 app/microsoft/token_broker.py 說明：缺測試 Entra Tenant）。
MVP 登入模型：
  - environment_slug 留空 → 比對 platform_local_logins（break-glass／platform operator）。
  - environment_slug 有值 → 比對該 Environment 的 environment_local_logins（D-03 若核准保留）。
兩種帳號各自獨立鎖定計數，比照現行系統 05-security-operations.md §2 沿用機制。
"""
from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.microsoft.sso import SsoError, SsoNotConfigured, build_auth_broker
from app.platform.audit import record_audit
from app.platform.models import (
    EnvironmentLocalLogin,
    ExternalLogin,
    ManagementEnvironment,
    PlatformLocalLogin,
    Principal,
)
from app.platform.security import normalize_username, verify_password
from app.storage.time_utils import utc_now_naive
from app.web.auth.forms import LoginForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

MAX_FAILED_LOGIN = 5
LOCK_MINUTES = 15


def _lock_if_needed(login_row) -> None:
    login_row.failed_login_count += 1
    if login_row.failed_login_count >= MAX_FAILED_LOGIN:
        from datetime import timedelta
        login_row.locked_until = utc_now_naive() + timedelta(minutes=LOCK_MINUTES)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("environments.list_environments"))

    form = LoginForm()
    if form.validate_on_submit():
        username = normalize_username(form.username.data)
        password = form.password.data
        slug = (form.environment_slug.data or "").strip().lower()

        if slug:
            environment = ManagementEnvironment.query.filter_by(slug=slug, status="active").first()
            if environment is None:
                flash("環境代碼不存在或未啟用", "danger")
                return render_template("auth/login.html", form=form)
            login_row = EnvironmentLocalLogin.query.filter_by(
                environment_id=environment.id, normalized_username=username,
            ).first()
            if login_row is None or login_row.is_locked() or not verify_password(password, login_row.password_hash):
                if login_row is not None and not login_row.is_locked():
                    _lock_if_needed(login_row)
                    db.session.commit()
                flash("帳號或密碼錯誤", "danger")
                return render_template("auth/login.html", form=form)
            login_row.failed_login_count = 0
            login_row.locked_until = None
            db.session.commit()
            principal = db.session.get(Principal, login_row.principal_id)
            login_user(principal)
            session["active_environment_id"] = None
            session.pop("active_managed_tenant_id", None)
            record_audit(
                environment_id=environment.id, actor_principal_id=principal.id,
                action="login.environment_local", target_type="principal", target_id=principal.id,
            )
            db.session.commit()
            return _switch_to_environment(environment)

        login_row = PlatformLocalLogin.query.filter_by(normalized_username=username).first()
        if login_row is None or login_row.is_locked() or not verify_password(password, login_row.password_hash):
            if login_row is not None and not login_row.is_locked():
                _lock_if_needed(login_row)
                db.session.commit()
            flash("帳號或密碼錯誤", "danger")
            return render_template("auth/login.html", form=form)
        login_row.failed_login_count = 0
        login_row.locked_until = None
        db.session.commit()
        principal = db.session.get(Principal, login_row.principal_id)
        login_user(principal)
        session.pop("active_environment_id", None)
        session.pop("active_managed_tenant_id", None)
        return redirect(url_for("environments.list_environments"))

    return render_template("auth/login.html", form=form)


def _switch_to_environment(environment: ManagementEnvironment):
    from app.platform.models import EnvironmentMembership
    membership = EnvironmentMembership.query.filter_by(
        environment_id=environment.id, principal_id=current_user.id, status="active",
    ).first()
    if membership is None:
        flash("此帳號沒有此環境的有效成員資格", "danger")
        logout_user()
        return redirect(url_for("auth.login"))
    session["active_environment_id"] = str(environment.id)
    session["membership_version_seen"] = membership.version
    session.pop("active_managed_tenant_id", None)
    return redirect(url_for("managed_tenants.list_managed_tenants"))


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.pop("active_environment_id", None)
    session.pop("membership_version_seen", None)
    session.pop("active_managed_tenant_id", None)
    logout_user()
    return redirect(url_for("auth.login"))


# ── Entra SSO 使用者登入（Phase D）───────────────────────────────────────────
# broker 取得：測試注入 app.config["ENTRA_AUTH_BROKER"]（避免真的建 MSAL app／打網路）；
# 否則依 config 建真的 broker，未啟用時丟 SsoNotConfigured → route 轉 404。
def _entra_broker():
    injected = current_app.config.get("ENTRA_AUTH_BROKER")
    if injected is not None:
        return injected
    return build_auth_broker(current_app.config)


def _entra_redirect_uri() -> str:
    return current_app.config.get("ENTRA_LOGIN_REDIRECT_URI") or url_for(
        "auth.entra_callback", _external=True,
    )


def _begin_entra_flow(mode: str):
    try:
        broker = _entra_broker()
    except SsoNotConfigured:
        abort(404)
    flow = broker.begin(redirect_uri=_entra_redirect_uri())
    # flow 含 state/nonce/PKCE code_verifier，一次性存 session；callback 取用後即丟棄。
    session["entra_auth_flow"] = flow
    session["entra_flow_mode"] = mode
    return redirect(flow["auth_uri"])


@auth_bp.route("/entra/login")
def entra_login():
    if current_user.is_authenticated:
        return redirect(url_for("environments.list_environments"))
    return _begin_entra_flow("login")


@auth_bp.route("/entra/link")
@login_required
def entra_link():
    """已登入者把自己的 Entra 身分綁定到目前 Principal（之後可改用 SSO 登入）。"""
    return _begin_entra_flow("link")


@auth_bp.route("/entra/callback")
def entra_callback():
    try:
        broker = _entra_broker()
    except SsoNotConfigured:
        abort(404)
    flow = session.pop("entra_auth_flow", None)
    mode = session.pop("entra_flow_mode", "login")
    if not flow:
        flash("登入流程已逾時或無效，請重試", "danger")
        return redirect(url_for("auth.login"))
    try:
        identity = broker.complete(flow, request.args.to_dict())
    except SsoError:
        flash("Entra 登入失敗，請重試或改用本地帳號", "danger")
        return redirect(url_for("auth.login"))
    if mode == "link":
        return _entra_link_identity(identity)
    return _entra_login_identity(identity)


def _entra_login_identity(identity: dict):
    binding = ExternalLogin.query.filter_by(
        canonical_issuer=identity["canonical_issuer"], subject=identity["subject"],
    ).first()
    if binding is None:
        # fail-closed：未綁定的 Entra 身分不得自動開帳號（禁 email/UPN 自動配對）。
        flash("此 Entra 身分尚未綁定帳號；請先以本地帳號登入並於「綁定 Entra 登入」完成綁定，或聯絡平台管理者。", "danger")
        return redirect(url_for("auth.login"))
    principal = db.session.get(Principal, binding.principal_id)
    if principal is None or not principal.is_active:
        flash("此帳號已停用", "danger")
        return redirect(url_for("auth.login"))
    login_user(principal)
    session.pop("active_environment_id", None)
    session.pop("membership_version_seen", None)
    session.pop("active_managed_tenant_id", None)
    return redirect(url_for("environments.list_environments"))


def _entra_link_identity(identity: dict):
    existing = ExternalLogin.query.filter_by(
        canonical_issuer=identity["canonical_issuer"], subject=identity["subject"],
    ).first()
    if existing is not None:
        if existing.principal_id == current_user.id:
            flash("此 Entra 身分已綁定你的帳號", "info")
        else:
            # 已綁到別人 → 拒絕，避免同一 (iss,sub) 被多個 Principal 搶綁造成帳號接管。
            flash("此 Entra 身分已綁定其他帳號，無法重複綁定", "danger")
        return redirect(url_for("environments.list_environments"))
    db.session.add(ExternalLogin(
        principal_id=current_user.id,
        canonical_issuer=identity["canonical_issuer"],
        subject=identity["subject"],
        issuer_tenant_id=identity.get("issuer_tenant_id"),
        object_id=identity.get("object_id"),
    ))
    db.session.commit()
    flash("已成功綁定 Entra 登入身分，日後可用 Entra 帳號登入", "success")
    return redirect(url_for("environments.list_environments"))
