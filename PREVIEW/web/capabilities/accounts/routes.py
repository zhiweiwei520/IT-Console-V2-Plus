"""
accounts capability 的 web 殼層：route 只做「解析 request → 呼叫 service → 組 response」的薄殼
（ADR-007 §4.3）。business logic 在 app/capabilities/accounts/service.py，該檔不 import flask。
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.capabilities.accounts.service import AccountService
from app.extensions import db
from app.jobs.dispatcher import AccountsSyncDispatcher
from app.web.context import NoActiveEnvironment, NoActiveTenant, require_tenant_context

accounts_bp = Blueprint("accounts", __name__, url_prefix="/capabilities/accounts")


@accounts_bp.route("/")
@login_required
def list_accounts():
    try:
        context = require_tenant_context("accounts.view", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        flash("請先選擇要管理的 Tenant", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    service = AccountService(db.session, context)
    accounts = service.list_accounts()
    return render_template(
        "capabilities/accounts/list.html",
        accounts=accounts,
        context=context,
    )


@accounts_bp.route("/sync", methods=["POST"])
@login_required
def sync_accounts():
    try:
        context = require_tenant_context("accounts.sync", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        flash("請先選擇要管理的 Tenant", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    dispatcher = AccountsSyncDispatcher(db.session, context)
    try:
        dispatcher.enqueue(context.active_managed_tenant_id)
    except (PermissionError, ValueError) as exc:
        db.session.rollback()
        flash(f"無法排入同步工作：{exc}", "danger")
        return redirect(url_for("accounts.list_accounts"))
    db.session.commit()
    flash("已排入同步工作，背景 worker 會自動處理；稍候重新整理頁面即可看到結果。", "success")
    return redirect(url_for("accounts.list_accounts"))
