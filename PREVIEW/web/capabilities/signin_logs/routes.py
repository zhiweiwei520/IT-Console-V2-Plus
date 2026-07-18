"""
signin_logs capability 的 web 殼層（薄殼，ADR-007 §4.3）。business logic 在
app/capabilities/signin_logs/service.py，該檔不 import flask。結構比照 accounts/devices routes。
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.capabilities.signin_logs.service import SignInLogService
from app.extensions import db
from app.jobs.dispatcher import SignInLogsSyncDispatcher
from app.web.context import NoActiveEnvironment, NoActiveTenant, require_tenant_context

signin_logs_bp = Blueprint("signin_logs", __name__, url_prefix="/capabilities/signin-logs")


@signin_logs_bp.route("/")
@login_required
def list_sign_ins():
    try:
        context = require_tenant_context("signin_logs.view", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        flash("請先選擇要管理的 Tenant", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    service = SignInLogService(db.session, context)
    sign_ins = service.list_recent()
    return render_template(
        "capabilities/signin_logs/list.html",
        sign_ins=sign_ins,
        context=context,
    )


@signin_logs_bp.route("/sync", methods=["POST"])
@login_required
def sync_sign_ins():
    try:
        context = require_tenant_context("signin_logs.sync", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        flash("請先選擇要管理的 Tenant", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    dispatcher = SignInLogsSyncDispatcher(db.session, context)
    try:
        dispatcher.enqueue(context.active_managed_tenant_id)
    except (PermissionError, ValueError) as exc:
        db.session.rollback()
        flash(f"無法排入同步工作：{exc}", "danger")
        return redirect(url_for("signin_logs.list_sign_ins"))
    db.session.commit()
    flash("已排入登入記錄增量同步工作，背景 worker 會自動處理；稍候重新整理頁面即可看到結果。", "success")
    return redirect(url_for("signin_logs.list_sign_ins"))
