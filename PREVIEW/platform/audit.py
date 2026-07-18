"""
Environment audit hash chain 寫入與驗證 helper。

每個 Environment 以獨立 chain head 序列化寫入。呼叫端仍負責讓 mutation、audit 與 commit
位於同一 transaction。簽章／anchor 見 app/platform/audit_signing.py、audit_anchor.py；
本檔只負責 DB 內鏈本身的寫入與「內部自洽性」驗證（verify_audit_chain）。單靠內部自洽性
無法偵測「攻擊者已能改 DB、把整條鏈重新算過」的情境，這正是 verify_chain_against_anchor
存在的原因：拿外部（anchor 檔案）記下的某個歷史檢查點，回頭比對 DB 現況是否仍然一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import uuid

from sqlalchemy import select

from app.extensions import db
from app.platform.models import (
    EnvironmentAuditChainHead,
    EnvironmentAuditLog,
    ManagementEnvironment,
)
from app.storage.time_utils import utc_now_naive

GENESIS_HASH = "0" * 64
HASH_VERSION = 1


def _canonical_uuid(value) -> str | None:
    return str(uuid.UUID(str(value))) if value is not None else None


def _canonical_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def compute_entry_hash(entry: EnvironmentAuditLog) -> str:
    payload = {
        "action": entry.action,
        "actor_principal_id": _canonical_uuid(entry.actor_principal_id),
        "chain_sequence": entry.chain_sequence,
        "correlation_id": entry.correlation_id,
        "created_at": _canonical_timestamp(entry.created_at),
        "entry_id": _canonical_uuid(entry.id),
        "environment_id": _canonical_uuid(entry.environment_id),
        "hash_version": entry.hash_version,
        "outcome": entry.outcome,
        "previous_hash": entry.previous_hash,
        "reason": entry.reason,
        "target_id": entry.target_id,
        "target_type": entry.target_type,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AuditChainVerification:
    valid: bool
    entry_count: int
    error: str | None = None


def record_audit(
    *,
    environment_id,
    actor_principal_id,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    outcome: str = "success",
    reason: str | None = None,
    correlation_id: str | None = None,
) -> EnvironmentAuditLog:
    locked_environment = db.session.execute(
        select(ManagementEnvironment.id)
        .where(ManagementEnvironment.id == environment_id)
        .with_for_update()
    ).scalar_one_or_none()
    if locked_environment is None:
        raise ValueError("Cannot record audit for an unknown environment")

    head = db.session.get(EnvironmentAuditChainHead, environment_id)
    if head is None:
        head = EnvironmentAuditChainHead(
            environment_id=environment_id,
            last_sequence=0,
            last_hash=GENESIS_HASH,
            updated_at=utc_now_naive(),
        )
        db.session.add(head)

    entry = EnvironmentAuditLog(
        id=uuid.uuid4(),
        environment_id=environment_id,
        actor_principal_id=actor_principal_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        outcome=outcome,
        reason=reason,
        correlation_id=correlation_id or str(uuid.uuid4()),
        created_at=utc_now_naive(),
        chain_sequence=head.last_sequence + 1,
        previous_hash=head.last_hash,
        hash_version=HASH_VERSION,
    )
    entry.entry_hash = compute_entry_hash(entry)
    db.session.add(entry)
    head.last_sequence = entry.chain_sequence
    head.last_hash = entry.entry_hash
    head.updated_at = entry.created_at
    return entry


def verify_audit_chain(environment_id) -> AuditChainVerification:
    entries = db.session.execute(
        select(EnvironmentAuditLog)
        .where(EnvironmentAuditLog.environment_id == environment_id)
        .order_by(EnvironmentAuditLog.chain_sequence)
    ).scalars().all()

    expected_previous = GENESIS_HASH
    for expected_sequence, entry in enumerate(entries, start=1):
        if entry.chain_sequence != expected_sequence:
            return AuditChainVerification(False, len(entries), "chain sequence is not contiguous")
        if entry.previous_hash != expected_previous:
            return AuditChainVerification(False, len(entries), "previous hash mismatch")
        if entry.entry_hash != compute_entry_hash(entry):
            return AuditChainVerification(False, len(entries), "entry hash mismatch")
        expected_previous = entry.entry_hash

    head = db.session.get(EnvironmentAuditChainHead, environment_id)
    expected_sequence = len(entries)
    if head is None:
        if entries:
            return AuditChainVerification(False, len(entries), "chain head is missing")
        return AuditChainVerification(True, 0)
    if head.last_sequence != expected_sequence or head.last_hash != expected_previous:
        return AuditChainVerification(False, len(entries), "chain head mismatch")
    return AuditChainVerification(True, len(entries))


def verify_chain_against_anchor(environment_id, anchor) -> AuditChainVerification:
    """在 verify_audit_chain 之外，額外比對一個外部 anchor 檢查點。

    anchor 需有 chain_sequence／chain_hash／signature_valid() —— 見
    app/platform/audit_anchor.py::AnchorRecord。偵測兩種內部自洽性測不出來的竄改：
      1. anchor 本身簽章對不上（anchor 檔案被改，或用錯 master key 驗）。
      2. DB 現況在 anchor 記錄的 sequence 之後被整條重新計算過（歷史被改寫但保持自洽）。
      3. DB chain 目前長度小於 anchor 記錄的 sequence（audit rows 被刪除／回退）。
    """
    internal = verify_audit_chain(environment_id)
    if not internal.valid:
        return internal

    if not anchor.signature_valid():
        return AuditChainVerification(False, internal.entry_count, "anchor signature is invalid")

    if internal.entry_count < anchor.chain_sequence:
        return AuditChainVerification(
            False, internal.entry_count,
            f"chain has fewer entries ({internal.entry_count}) than anchored sequence ({anchor.chain_sequence})",
        )

    anchored_entry = db.session.execute(
        select(EnvironmentAuditLog).where(
            EnvironmentAuditLog.environment_id == environment_id,
            EnvironmentAuditLog.chain_sequence == anchor.chain_sequence,
        )
    ).scalar_one_or_none()
    if anchored_entry is None or anchored_entry.entry_hash != anchor.chain_hash:
        return AuditChainVerification(
            False, internal.entry_count,
            "DB entry at anchored sequence no longer matches the anchor (history was rewritten)",
        )
    return AuditChainVerification(True, internal.entry_count)
