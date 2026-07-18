"""
devices capability 的 web 殼層：route 只做「解析 request → 呼叫 service → 組 response」的薄殼
（ADR-007 §4.3）。business logic 在 app/capabilities/devices/service.py，該檔不 import flask。
結構比照 app/web/capabilities/accounts/routes.py。
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.capabilities.devices.service import DeviceService
from app.extensions import db
from app.jobs.dispatcher import DevicesSyncDispatcher
from app.web.context import NoActiveEnvironment, NoActiveTenant, require_tenant_context

devices_bp = Blueprint("devices", __name__, url_prefix="/capabilities/devices")


@devices_bp.route("/")
@login_required
def list_devices():
    try:
        context = require_tenant_context("devices.view", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        flash("請先選擇要管理的 Tenant", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    service = DeviceService(db.session, context)
    devices = service.list_devices()
    return render_template(
        "capabilities/devices/list.html",
        devices=devices,
        context=context,
    )


@devices_bp.route("/sync", methods=["POST"])
@login_required
def sync_devices():
    try:
        context = require_tenant_context("devices.sync", require_active_tenant=True)
    except NoActiveEnvironment:
        return redirect(url_for("environments.list_environments"))
    except NoActiveTenant:
        flash("請先選擇要管理的 Tenant", "warning")
        return redirect(url_for("managed_tenants.list_managed_tenants"))

    dispatcher = DevicesSyncDispatcher(db.session, context)
    try:
        dispatcher.enqueue(context.active_managed_tenant_id)
    except (PermissionError, ValueError) as exc:
        db.session.rollback()
        flash(f"無法排入同步工作：{exc}", "danger")
        return redirect(url_for("devices.list_devices"))
    db.session.commit()
    flash("已排入裝置同步工作，背景 worker 會自動處理；稍候重新整理頁面即可看到結果。", "success")
    return redirect(url_for("devices.list_devices"))
