"""
Control Plane service：環境生命週期與成員管理的共用邏輯。

09-development-standards.md §1：`control_plane/` 負責 catalog／placement／provisioning；
MVP 以這幾個函式取代獨立服務，`manage.py` CLI 與 `app/web/platform/routes.py` 網頁介面
共用同一份邏輯，避免兩邊各自實作、行為分岔（曾在別處踩過這種坑，見 capability-manifest）。

這裡刻意不 import flask（ADR-007 §4.3 邊界規則）；呼叫端（CLI／web route）各自負責把
使用者輸入轉成這裡的參數，並把 ValueError 轉成對應的錯誤呈現方式。
"""
from __future__ import annotations

from app.extensions import db
from app.platform.models import (
    EnvironmentMembership,
    EnvironmentRole,
    ManagementEnvironment,
    MembershipTenantGrant,
    PlatformLocalLogin,
    PlatformRoleAssignment,
    Principal,
    RoleAssignment,
)
from app.platform.permissions import ensure_environment_builtin_roles
from app.platform.security import hash_password, normalize_username, password_policy_errors
from app.storage.time_utils import utc_now_naive


def create_principal(
    display_name: str,
    *,
    platform_username: str | None = None,
    platform_password: str | None = None,
    platform_operator: bool = False,
) -> Principal:
    display_name = (display_name or "").strip()
    if not display_name:
        raise ValueError("display_name 不可為空")

    principal = Principal(display_name=display_name)
    db.session.add(principal)
    db.session.flush()

    if platform_username:
        username = normalize_username(platform_username)
        if PlatformLocalLogin.query.filter_by(normalized_username=username).first() is not None:
            raise ValueError(f"帳號 '{username}' 已存在")
        if not platform_password:
            raise ValueError("設定 platform_username 時必須提供 platform_password")
        errors = password_policy_errors(platform_password)
        if errors:
            raise ValueError("密碼不符合政策：" + "；".join(errors))
        db.session.add(PlatformLocalLogin(
            principal_id=principal.id,
            normalized_username=username,
            password_hash=hash_password(platform_password),
        ))

    if platform_operator:
        db.session.add(PlatformRoleAssignment(
            principal_id=principal.id, role_code="platform_operator", granted_at=utc_now_naive(),
        ))

    db.session.commit()
    return principal


def create_environment(slug: str, name: str) -> ManagementEnvironment:
    slug = (slug or "").strip().lower()
    name = (name or "").strip()
    if not slug:
        raise ValueError("slug 不可為空")
    if not name:
        raise ValueError("name 不可為空")
    if ManagementEnvironment.query.filter_by(slug=slug).first() is not None:
        raise ValueError(f"slug '{slug}' 已存在")

    env = ManagementEnvironment(slug=slug, name=name, status="active")
    db.session.add(env)
    db.session.commit()
    ensure_environment_builtin_roles(env.id)
    return env


def add_membership(
    environment: ManagementEnvironment,
    principal: Principal,
    *,
    role_code: str,
    all_managed_tenants: bool = False,
    managed_tenant_ids: list | None = None,
) -> EnvironmentMembership:
    role = EnvironmentRole.query.filter_by(environment_id=environment.id, code=role_code).first()
    if role is None:
        raise ValueError(f"環境 '{environment.slug}' 沒有角色 '{role_code}'")

    membership = EnvironmentMembership.query.filter_by(
        environment_id=environment.id, principal_id=principal.id,
    ).first()
    if membership is None:
        membership = EnvironmentMembership(
            environment_id=environment.id, principal_id=principal.id,
            all_managed_tenants=all_managed_tenants,
        )
        db.session.add(membership)
        db.session.flush()
    else:
        membership.all_managed_tenants = all_managed_tenants
        membership.version += 1

    if RoleAssignment.query.filter_by(membership_id=membership.id, role_id=role.id).first() is None:
        db.session.add(RoleAssignment(
            environment_id=environment.id, membership_id=membership.id, role_id=role.id,
            granted_at=utc_now_naive(),
        ))

    if not all_managed_tenants:
        for tenant_id in (managed_tenant_ids or []):
            if MembershipTenantGrant.query.filter_by(
                membership_id=membership.id, managed_tenant_id=tenant_id,
            ).first() is None:
                db.session.add(MembershipTenantGrant(
                    environment_id=environment.id, membership_id=membership.id, managed_tenant_id=tenant_id,
                ))

    db.session.commit()
    return membership
