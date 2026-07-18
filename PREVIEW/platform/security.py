"""密碼雜湊 helper（沿用 werkzeug 內建 PBKDF2，與現行系統機制一致，見 05-security-operations.md §2）。"""
from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

MIN_PASSWORD_LENGTH = 12


def hash_password(raw: str) -> str:
    return generate_password_hash(raw)


def verify_password(raw: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, raw)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def password_policy_errors(raw: str) -> list[str]:
    errors = []
    if len(raw) < MIN_PASSWORD_LENGTH:
        errors.append(f"密碼長度至少需 {MIN_PASSWORD_LENGTH} 碼")
    if not any(c.isupper() for c in raw):
        errors.append("密碼須包含至少一個大寫字母")
    if not any(c.isdigit() for c in raw):
        errors.append("密碼須包含至少一個數字")
    return errors
