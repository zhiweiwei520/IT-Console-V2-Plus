"""dashboard service — 跨模組唯讀 KPI 聚合（roadmap Phase C8）。

安全鐵則（root CLAUDE.md Issue #5）：KPI 由**後端依權限條件查詢**——無該 capability view
權限的模組**根本不查、不進 context**，template 不可能洩漏數字。所有計數沿用
`TenantScopedRepository` 的單一目前 Tenant fail-closed scoping（缺 active tenant 直接拒絕）。
"""
from __future__ import annotations
from app.storage.repository import TenantScopedRepository
from app.capabilities.accounts.models import Account
from app.capabilities.devices.models import Device
from app.capabilities.signin_logs.models import SignInLog
from app.capabilities.licenses.models import LicenseSku
from app.capabilities.app_audit.models import AppRegistration
from app.capabilities.software.models import DetectedSoftware
from app.capabilities.teams.models import TeamAudit
from app.capabilities.sharepoint.models import SharePointSiteAudit
from app.capabilities.defender.models import DefenderAlert
from app.capabilities.sentinel.models import SecurityIncident

# (view 權限, 顯示標籤, model)；順序即卡片呈現順序。
_KPI_SPECS = [
    ("accounts.view", "帳號", Account),
    ("devices.view", "裝置", Device),
    ("signin_logs.view", "登入記錄", SignInLog),
    ("licenses.view", "授權 SKU", LicenseSku),
    ("app_audit.view", "App 註冊", AppRegistration),
    ("software.view", "偵測軟體", DetectedSoftware),
    ("teams.view", "Teams 團隊", TeamAudit),
    ("sharepoint.view", "SharePoint 網站", SharePointSiteAudit),
    ("defender.view", "Defender 告警", DefenderAlert),
    ("sentinel.view", "資安事件", SecurityIncident),
]


class _ScopedCount(TenantScopedRepository):
    """借用 TenantScopedRepository 的 environment+單一 Tenant scoping 做計數；model 動態注入。"""
    model = None
    def __init__(self, session, context, model):
        self.model = model  # 先設 instance 屬性，才過 ScopedRepository.__init__ 的 model is None 檢查
        super().__init__(session, context)
    def count(self):
        return self._base_query().count()


class DashboardService:
    def __init__(self, session, context):
        self.session = session
        self.context = context

    def kpis(self):
        cards = []
        for perm, label, model in _KPI_SPECS:
            if not self.context.has_permission(perm):
                continue  # 後端 gate：無權限不查（Issue #5）
            cards.append({"label": label, "value": _ScopedCount(self.session, self.context, model).count(), "permission": perm})
        return cards
