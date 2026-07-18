"""Tenant-scoped GraphClient factory。"""
from __future__ import annotations

from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.microsoft.credentials import CompositeCredentialProvider
from app.microsoft.graph_client import HttpGraphClient
from app.microsoft.models import ManagedTenant, TenantConnection
from app.microsoft.token_broker import MsalTokenBroker, TokenBroker


class GraphClientFactoryError(RuntimeError):
    pass


class TenantGraphClientFactory:
    def __init__(
        self,
        session: Session,
        token_broker: TokenBroker,
        *,
        http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.session = session
        self.token_broker = token_broker
        self.http_client_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False)
        )

    def __call__(self, environment_id, managed_tenant_id, *, include_pending: bool = False) -> HttpGraphClient:
        """include_pending：剛透過 BYO app 表單建立、尚未驗證過的連線也是 pending 狀態；
        「測試連線」這個動作本身就是要驗證一個還沒被信任的連線，所以需要一個明確的例外路徑
        （預設 False，Worker 走正常 sync 絕不能用 pending 連線，見 09 §2 fail-closed 原則）。"""
        tenant_statuses = ("active", "degraded", "pending") if include_pending else ("active", "degraded")
        connection_statuses = ("active", "pending") if include_pending else ("active",)

        tenant = self.session.execute(
            select(ManagedTenant).where(
                ManagedTenant.id == managed_tenant_id,
                ManagedTenant.environment_id == environment_id,
                ManagedTenant.status.in_(tenant_statuses),
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise GraphClientFactoryError("managed_tenant_unavailable")
        connection = self.session.execute(
            select(TenantConnection).where(
                TenantConnection.environment_id == environment_id,
                TenantConnection.managed_tenant_id == managed_tenant_id,
                TenantConnection.status.in_(connection_statuses),
            )
        ).scalar_one_or_none()
        if connection is None:
            raise GraphClientFactoryError("tenant_connection_unavailable")
        return HttpGraphClient(
            self.token_broker, tenant, connection, self.http_client_factory(),
        )


# 模組層級單例：MsalTokenBroker 內部快取 ConfidentialClientApplication（依 token cache key，
# 04 §6），必須跨呼叫存活，否則每次 Worker claim 一個 job 就重建、失去快取意義。
# CompositeCredentialProvider 本身無狀態，僅為求對稱一併固定成單例。
_default_credential_provider = CompositeCredentialProvider()
_default_token_broker = MsalTokenBroker(_default_credential_provider)


def default_graph_client_factory(environment_id, managed_tenant_id, *, include_pending: bool = False) -> HttpGraphClient:
    """開箱即用的 GraphClientFactory：`V2PLUS_GRAPH_CLIENT_FACTORY=app.microsoft.factory:default_graph_client_factory`。

    session 刻意在呼叫當下才取 `db.session`（Flask-SQLAlchemy scoped session），不在模組
    載入時綁定，因為 Worker 於 `app.app_context()` 內執行，取用時機才有正確的 app context。
    支援兩種 credential_ref：`env:V2PLUS_*`（維運人員手動設 OS 環境變數）與
    `db:<connection_id>`（使用者透過網頁表單自助輸入，見 app/web/microsoft/routes.py）。
    """
    from app.extensions import db

    factory = TenantGraphClientFactory(db.session, _default_token_broker)
    return factory(environment_id, managed_tenant_id, include_pending=include_pending)
