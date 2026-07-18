"""
BYO app client secret 對稱加密（Fernet）。

11-final-architecture.md §3.2：Key Vault 是正式目標，credential reference 模型從第一天就要
對；本檔是「DB 內加密存放」這條 dev/self-host 過渡路徑的加解密實作——密文才進 DB，明文只在
記憶體內短暫存在，且只有拿得到 V2PLUS_ENCRYPTION_KEY 的 process 解得開（04 §2：BYO app
憑證政策放寬為「憑證優先；客戶堅持 secret 時限短效＋到期告警＋輪替 runbook」，本檔是其中
「secret 存放」的最小可用版本，尚未做到期告警／輪替）。
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class EncryptionKeyUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    raw = os.environ.get("V2PLUS_ENCRYPTION_KEY", "")
    if not raw:
        raise EncryptionKeyUnavailable("V2PLUS_ENCRYPTION_KEY 未設定，無法加密／解密憑證。")
    try:
        return Fernet(raw.encode("utf-8"))
    except ValueError as exc:
        raise EncryptionKeyUnavailable(
            "V2PLUS_ENCRYPTION_KEY 格式不正確；需為 Fernet.generate_key() 產生的 base64 值。"
        ) from exc


def encrypt_secret(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionKeyUnavailable(
            "credential ciphertext 無法解密（金鑰不符，或密文已損毀）。"
        ) from exc
