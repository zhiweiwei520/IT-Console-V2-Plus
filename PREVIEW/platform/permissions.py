"""
Environment 角色權限目錄。命名慣例沿用 CLAUDE.md B4：dot notation `<namespace>.<verb>`。

MVP 範圍僅 accounts capability 一個垂直切片；新增權限時比照 09 §10 Definition of Done：
本檔加 code → BUILTIN_ROLE_PERMISSIONS 加角色授權 → 三層 gating（sidebar／route）同步落實。
"""
from __future__ import annotations

from app.extensions import db
from app.platform.models import EnvironmentRole, Permission, PlatformRoleAssignment, RolePermission
from app.storage.time_utils import utc_now_naive

# (code, label, category)
BUILTIN_PERMISSIONS: list[tuple[str, str, str]] = [
    ("environment.members.manage", "管理環境成員與角色", "environment"),
    ("environment.tenants.manage", "管理受管 Tenant", "environment"),
    ("accounts.view", "查看帳號清單", "accounts"),
    ("accounts.sync", "同步帳號資料", "accounts"),
    ("devices.view", "查看裝置清單", "devices"),
    ("devices.sync", "同步裝置資料", "devices"),
    ("signin_logs.view", "查看登入記錄", "signin_logs"),
    ("signin_logs.sync", "同步登入記錄", "signin_logs"),
    ("licenses.view", "查看授權與 MFA 稽核", "licenses"),
    ("licenses.sync", "同步授權與 MFA 稽核", "licenses"),
    ("app_audit.view", "查看應用程式稽核", "app_audit"),
    ("app_audit.sync", "同步應用程式稽核", "app_audit"),
    ("software.view", "查看 Intune 軟體清冊", "software"),
    ("software.sync", "同步 Intune 軟體清冊", "software"),
    ("teams.view", "查看 Teams 團隊", "teams"),
    ("teams.sync", "同步 Teams 團隊", "teams"),
    ("sharepoint.view", "查看 SharePoint 網站", "sharepoint"),
    ("sharepoint.sync", "同步 SharePoint 網站", "sharepoint"),
    ("defender.view", "查看 Defender 告警", "defender"),
    ("defender.sync", "同步 Defender 告警", "defender"),
    ("sentinel.view", "查看資安事件", "sentinel"),
    ("sentinel.sync", "同步資安事件", "sentinel"),
]

# environment role code -> permission codes
BUILTIN_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "environment_admin": [
        "environment.members.manage",
        "environment.tenants.manage",
        "accounts.view",
        "accounts.sync",
        "devices.view",
        "devices.sync",
        "signin_logs.view",
        "signin_logs.sync",
        "licenses.view",
        "licenses.sync",
        "app_audit.view", "app_audit.sync",
        "software.view", "software.sync",
        "teams.view", "teams.sync",
        "sharepoint.view", "sharepoint.sync",
        "defender.view", "defender.sync",
        "sentinel.view", "sentinel.sync",
    ],
    "viewer": [
        "accounts.view",
        "devices.view",
        "signin_logs.view",
        "licenses.view",
        "app_audit.view",
        "software.view",
        "teams.view",
        "sharepoint.view",
        "defender.view",
        "sentinel.view",
    ],
}

BUILTIN_ENVIRONMENT_ROLES: list[tuple[str, str]] = [
    ("environment_admin", "環境管理者"),
    ("viewer", "唯讀"),
]


def is_platform_operator(principal_id) -> bool:
    """05-security-operations.md §3：platform_operator 只管生命週期，不隱含任何 Environment
    資料存取——這裡刻意只回答「是不是 platform operator」，不會被拿來當 Environment 權限用。"""
    return PlatformRoleAssignment.query.filter_by(
        principal_id=principal_id, role_code="platform_operator",
    ).first() is not None


def ensure_builtin_permissions() -> None:
    """Idempotent：同步權限目錄（不刪除既有自訂權限）。"""
    existing = {p.code: p for p in Permission.query.all()}
    for code, label, category in BUILTIN_PERMISSIONS:
        p = existing.get(code)
        if p is None:
            db.session.add(Permission(code=code, label=label, category=category, is_builtin=True))
        else:
            p.label = label
            p.category = category
            p.is_builtin = True
    db.session.commit()


def ensure_environment_builtin_roles(environment_id) -> dict[str, EnvironmentRole]:
    """為指定 Environment 建立內建角色並同步權限授權（idempotent）。"""
    permission_by_code = {p.code: p for p in Permission.query.all()}
    roles: dict[str, EnvironmentRole] = {}

    for code, label in BUILTIN_ENVIRONMENT_ROLES:
        role = EnvironmentRole.query.filter_by(environment_id=environment_id, code=code).first()
        if role is None:
            role = EnvironmentRole(environment_id=environment_id, code=code, label=label, is_builtin=True)
            db.session.add(role)
            db.session.flush()
        roles[code] = role

    db.session.flush()

    for role_code, perm_codes in BUILTIN_ROLE_PERMISSIONS.items():
        role = roles[role_code]
        granted = {rp.permission_id for rp in RolePermission.query.filter_by(role_id=role.id).all()}
        for perm_code in perm_codes:
            perm = permission_by_code.get(perm_code)
            if perm is None or perm.id in granted:
                continue
            db.session.add(RolePermission(
                environment_id=environment_id,
                role_id=role.id,
                permission_id=perm.id,
                granted_at=utc_now_naive(),
            ))

    db.session.commit()
    return roles
