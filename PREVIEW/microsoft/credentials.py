"""Credential reference providers；DB 只保存 reference，不保存明文 secret。"""
from __future__ import annotations

import os
import re
import uuid
from typing import Protocol


class CredentialResolutionError(RuntimeError):
    pass


class CredentialProvider(Protocol):
    def get_secret(self, credential_ref: str) -> str: ...


class EnvironmentCredentialProvider:
    """開發／self-host 過渡方案；只接受 env:V2PLUS_* allowlist。
    需要維運人員先在 host 上手動設環境變數，不支援使用者自助輸入（見 DatabaseEncryptedCredentialProvider）。
    """

    _NAME_RE = re.compile(r"^V2PLUS_[A-Z0-9_]+$")

    def get_secret(self, credential_ref: str) -> str:
        if not credential_ref.startswith("env:"):
            raise CredentialResolutionError("unsupported credential reference scheme")
        name = credential_ref.removeprefix("env:")
        if not self._NAME_RE.fullmatch(name):
            raise CredentialResolutionError("credential environment variable is not allowed")
        value = os.environ.get(name, "")
        if not value:
            raise CredentialResolutionError("credential reference is unavailable")
        return value


class DatabaseEncryptedCredentialProvider:
    """BYO app 自助輸入方案：credential_ref 格式 `db:<tenant_connections.id>`，
    解密 TenantConnection.encrypted_client_secret（見 app/microsoft/encryption.py）。
    比 EnvironmentCredentialProvider 更適合「使用者透過網頁表單輸入」這種情境，因為
    不需要維運人員先手動設 OS 環境變數才能生效。"""

    _REF_PREFIX = "db:"

    def get_secret(self, credential_ref: str) -> str:
        if not credential_ref.startswith(self._REF_PREFIX):
            raise CredentialResolutionError("unsupported credential reference scheme")
        raw_id = credential_ref.removeprefix(self._REF_PREFIX)
        try:
            connection_id = uuid.UUID(raw_id)
        except ValueError as exc:
            raise CredentialResolutionError("invalid credential reference id") from exc

        from app.extensions import db
        from app.microsoft.models import TenantConnection

        connection = db.session.get(TenantConnection, connection_id)
        if connection is None or not connection.encrypted_client_secret:
            raise CredentialResolutionError("credential reference is unavailable")

        from app.microsoft.encryption import EncryptionKeyUnavailable, decrypt_secret
        try:
            return decrypt_secret(connection.encrypted_client_secret)
        except EncryptionKeyUnavailable as exc:
            raise CredentialResolutionError(str(exc)) from exc


class CompositeCredentialProvider:
    """依 credential_ref 的 scheme prefix（env: / db:）分派到對應 provider。"""

    def __init__(self, *, env_provider=None, db_provider=None) -> None:
        self.env_provider = env_provider or EnvironmentCredentialProvider()
        self.db_provider = db_provider or DatabaseEncryptedCredentialProvider()

    def get_secret(self, credential_ref: str) -> str:
        if credential_ref.startswith("env:"):
            return self.env_provider.get_secret(credential_ref)
        if credential_ref.startswith("db:"):
            return self.db_provider.get_secret(credential_ref)
        raise CredentialResolutionError("unsupported credential reference scheme")
