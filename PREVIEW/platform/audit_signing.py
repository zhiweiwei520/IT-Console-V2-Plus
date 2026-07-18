"""
Audit chain 簽章金鑰。

05-security-operations.md §5：「每 Environment 至少使用獨立 data-encryption／audit-signing
key scope」。此 spike 不依賴 Key Vault（見 11-final-architecture.md §3.2 file-based dev
provider 過渡方案），改用單一平台 master key 對 (environment_id) 做 HMAC 派生，取得每個
Environment 各自獨立、不需逐一手動 provision 的簽章金鑰。

⚠️ 已知限制：master key 與一般應用程式碼跑在同一個 process／權限邊界內，簽章無法防禦
「攻擊者已取得 app 執行環境完整存取權」這種情境（此時攻擊者能重算整條 chain 也能重簽）。
真正的威脅模型效益，需搭配 09 §7 已規劃、但本 spike 未實作的「chain writer 專用 DB role
與應用程式一般 role 分離」，讓一般 app role 連 UPDATE audit 表都做不到。這裡先把簽章與
anchor 的「形狀」與可驗證性做對，key 管理／role 分離留給正式部署（見 capability-manifest）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid


class AuditSigningKeyUnavailable(RuntimeError):
    pass


def _master_key() -> bytes:
    raw = os.environ.get("V2PLUS_AUDIT_MASTER_KEY", "")
    if not raw:
        raise AuditSigningKeyUnavailable(
            "V2PLUS_AUDIT_MASTER_KEY 未設定；write-audit-anchor／verify-audit-chain 需要它才能簽章／驗章。"
        )
    return raw.encode("utf-8")


def derive_environment_signing_key(environment_id) -> bytes:
    """HMAC-SHA256(master_key, environment_id) 派生每個 Environment 專屬金鑰。"""
    message = str(uuid.UUID(str(environment_id))).encode("utf-8")
    return hmac.new(_master_key(), message, hashlib.sha256).digest()


def sign_chain_head(environment_id, *, chain_sequence: int, chain_hash: str) -> str:
    key = derive_environment_signing_key(environment_id)
    message = f"{environment_id}:{chain_sequence}:{chain_hash}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_chain_head_signature(environment_id, *, chain_sequence: int, chain_hash: str, signature: str) -> bool:
    try:
        expected = sign_chain_head(environment_id, chain_sequence=chain_sequence, chain_hash=chain_hash)
    except AuditSigningKeyUnavailable:
        raise
    return hmac.compare_digest(expected, signature)
