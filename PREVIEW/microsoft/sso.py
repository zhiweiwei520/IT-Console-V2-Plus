"""Entra SSO 使用者登入 Auth Broker（roadmap Phase D）。

安全設計：
- 授權碼流程委由 MSAL `initiate_auth_code_flow` / `acquire_token_by_auth_code_flow`——MSAL 內建
  state、nonce、PKCE 與 id_token 驗證（audience／issuer／簽章／exp／nonce），**不自刻 JWT 驗證**
  （自刻 JWT 驗證極易漏簽章或 aud/iss 比對，這裡刻意不做）。
- 身分 canonical key 固定 `(iss, sub)`，**禁 email/UPN fallback**（email/UPN 可被租戶改動或重用，
  拿來當主鍵會造成帳號接管；見 roadmap D3 與 `ExternalLogin` model）。
- authority 僅允許 `https://login.microsoftonline.com/`（公用雲），與 token_broker 同一邊界。
"""
from __future__ import annotations

import msal

from app.microsoft.credentials import EnvironmentCredentialProvider

_ALLOWED_AUTHORITY_PREFIX = "https://login.microsoftonline.com/"
_LOGIN_SCOPES = ["User.Read"]


class SsoError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SsoNotConfigured(RuntimeError):
    """SSO 未啟用或 Login App 未設定；route 應轉 404，不得洩漏是哪一種。"""


def canonical_identity(claims: dict) -> dict:
    """從**已由 MSAL 驗證過**的 id_token claims 取 (iss, sub) canonical key。

    缺 iss 或 sub 一律拒絕；**不**退回 email／UPN／preferred_username 當識別鍵。
    """
    issuer = str(claims.get("iss") or "").strip()
    subject = str(claims.get("sub") or "").strip()
    if not issuer or not subject:
        raise SsoError("sso_claims_incomplete")
    return {
        "canonical_issuer": issuer,
        "subject": subject,
        "issuer_tenant_id": (str(claims.get("tid") or "").strip() or None),
        "object_id": (str(claims.get("oid") or "").strip() or None),
    }


class EntraAuthBroker:
    def __init__(self, *, client_id, client_credential, authority,
                 application_factory=msal.ConfidentialClientApplication) -> None:
        if not authority.startswith(_ALLOWED_AUTHORITY_PREFIX):
            raise SsoError("authority_not_allowed")
        try:
            self._app = application_factory(
                client_id, client_credential=client_credential, authority=authority,
            )
        except ValueError as exc:
            # MSAL 建構時做 OIDC discovery，authority/tenant 無效丟原生 ValueError（見 token_broker 同坑）。
            raise SsoError("authority_validation_failed") from exc

    def begin(self, *, redirect_uri: str) -> dict:
        """回傳 MSAL flow dict（含 auth_uri／state／nonce／code_verifier）；呼叫端存進 session。"""
        return self._app.initiate_auth_code_flow(_LOGIN_SCOPES, redirect_uri=redirect_uri)

    def complete(self, flow: dict, auth_response: dict) -> dict:
        """以 session 內的 flow 驗證 callback 回應並換取／驗證 id_token，回傳 canonical identity。"""
        try:
            result = self._app.acquire_token_by_auth_code_flow(flow, auth_response)
        except ValueError as exc:
            # state 不符／缺 code／flow 損毀時 MSAL 丟 ValueError。
            raise SsoError("auth_response_invalid") from exc
        if not isinstance(result, dict) or result.get("error"):
            raise SsoError(result.get("error") if isinstance(result, dict) else "token_exchange_failed")
        claims = result.get("id_token_claims")
        if not isinstance(claims, dict):
            raise SsoError("id_token_claims_missing")
        return canonical_identity(claims)


def build_auth_broker(config, *, credential_provider=None) -> EntraAuthBroker:
    """依 app.config 建 broker；未啟用或未設定丟 SsoNotConfigured。"""
    if not config.get("ENTRA_SSO_ENABLED"):
        raise SsoNotConfigured("entra sso disabled")
    client_id = config.get("ENTRA_LOGIN_CLIENT_ID")
    credential_ref = config.get("ENTRA_LOGIN_CREDENTIAL_REF")
    tenant = config.get("ENTRA_LOGIN_TENANT") or "organizations"
    if not client_id or not credential_ref:
        raise SsoNotConfigured("entra login app not configured")
    provider = credential_provider or EnvironmentCredentialProvider()
    secret = provider.get_secret(credential_ref)
    return EntraAuthBroker(
        client_id=client_id, client_credential=secret,
        authority=f"{_ALLOWED_AUTHORITY_PREFIX}{tenant}",
    )
