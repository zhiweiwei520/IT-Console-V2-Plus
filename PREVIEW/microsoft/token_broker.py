"""Tenant-aware MSAL application token broker。"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
from typing import Callable, Protocol

import msal

from app.microsoft.credentials import CredentialProvider

GRAPH_RESOURCE = "https://graph.microsoft.com"


class TokenAcquisitionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TokenBroker(Protocol):
    def acquire_token(self, tenant, connection, *, resource: str = GRAPH_RESOURCE) -> str: ...


@dataclass(frozen=True)
class TokenCacheKey:
    credential_profile_id: str
    credential_version: int
    entra_tenant_id: str
    authority_cloud: str
    resource_audience: str
    normalized_scope_hash: str


class MsalTokenBroker:
    def __init__(
        self,
        credential_provider: CredentialProvider,
        *,
        application_factory: Callable = msal.ConfidentialClientApplication,
    ) -> None:
        self.credential_provider = credential_provider
        self.application_factory = application_factory
        self._applications: dict[TokenCacheKey, object] = {}
        self._lock = threading.Lock()

    def acquire_token(self, tenant, connection, *, resource: str = GRAPH_RESOURCE) -> str:
        if tenant.cloud != "public" or resource.rstrip("/") != GRAPH_RESOURCE:
            raise TokenAcquisitionError("cloud_or_resource_not_allowed")
        if not connection.client_id or not connection.credential_ref:
            raise TokenAcquisitionError("connection_credential_incomplete")
        scope = GRAPH_RESOURCE + "/.default"
        key = TokenCacheKey(
            credential_profile_id=str(connection.id),
            credential_version=connection.credential_version,
            entra_tenant_id=tenant.entra_tenant_id,
            authority_cloud=tenant.cloud,
            resource_audience=GRAPH_RESOURCE,
            normalized_scope_hash=hashlib.sha256(scope.encode("utf-8")).hexdigest(),
        )
        with self._lock:
            application = self._applications.get(key)
            if application is None:
                secret = self.credential_provider.get_secret(connection.credential_ref)
                try:
                    application = self.application_factory(
                        client_id=connection.client_id,
                        client_credential=secret,
                        authority=f"https://login.microsoftonline.com/{tenant.entra_tenant_id}",
                    )
                except ValueError as exc:
                    # MSAL 在建構 ConfidentialClientApplication 時就會用 authority 做一次
                    # OIDC discovery 網路呼叫；tenant id 不存在或格式錯誤時丟原生 ValueError，
                    # 不是我們定義的例外類別，實測命中：BYO app 表單填錯 tenant id 會讓
                    # 「測試連線」變成 500 而不是回報「連線失敗」（見 capability-manifest）。
                    raise TokenAcquisitionError("authority_validation_failed") from exc
                self._applications[key] = application
            try:
                result = application.acquire_token_for_client(scopes=[scope])
            except ValueError as exc:
                raise TokenAcquisitionError("authority_validation_failed") from exc
        token = result.get("access_token") if isinstance(result, dict) else None
        if not token:
            error_code = result.get("error") if isinstance(result, dict) else None
            allowed = {"invalid_client", "invalid_scope", "unauthorized_client"}
            raise TokenAcquisitionError(error_code if error_code in allowed else "token_acquisition_failed")
        return token
