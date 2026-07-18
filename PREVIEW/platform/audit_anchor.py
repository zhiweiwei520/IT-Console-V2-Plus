"""
Audit chain anchor：把 chain head 的簽章快照寫到 DB 之外的地方，讓「攻擊者已能改 DB」
這種情境仍可被偵測——單純的 hash chain 只保證內部自洽，一個能同時改寫所有後續 entry 的
攻擊者可以重新算出一條「內部一致但內容不同」的鏈；anchor 提供一個外部、獨立的檢查點。

生產目標是「具 immutability policy 的 Blob」（05-security-operations.md §5）；此檔案是
dev／self-host 過渡實作：anchor 寫到本機 append-only JSON Lines 檔。verify 時只讀檔案，
不信任、也不需要透過應用程式的 DB 連線去讀（可用完全獨立的程序/機器執行）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.platform.audit_signing import sign_chain_head, verify_chain_head_signature
from app.storage.time_utils import utc_now_naive


@dataclass(frozen=True)
class AnchorRecord:
    environment_id: str
    environment_slug: str
    chain_sequence: int
    chain_hash: str
    signature: str
    written_at: str

    def signature_valid(self) -> bool:
        return verify_chain_head_signature(
            self.environment_id,
            chain_sequence=self.chain_sequence,
            chain_hash=self.chain_hash,
            signature=self.signature,
        )


class LocalFileAuditAnchorWriter:
    """單一環境一個檔案：`<base_dir>/<slug>.jsonl`。每筆 append，不改寫既有行。"""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def _path_for(self, environment_slug: str) -> Path:
        return self.base_dir / f"{environment_slug}.jsonl"

    def write(self, *, environment_id, environment_slug: str, chain_sequence: int, chain_hash: str) -> AnchorRecord:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        signature = sign_chain_head(environment_id, chain_sequence=chain_sequence, chain_hash=chain_hash)
        record = AnchorRecord(
            environment_id=str(environment_id),
            environment_slug=environment_slug,
            chain_sequence=chain_sequence,
            chain_hash=chain_hash,
            signature=signature,
            written_at=utc_now_naive().isoformat(timespec="microseconds"),
        )
        path = self._path_for(environment_slug)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.__dict__, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_all(self, environment_slug: str) -> list[AnchorRecord]:
        path = self._path_for(environment_slug)
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(AnchorRecord(**json.loads(line)))
        return records

    def latest(self, environment_slug: str) -> AnchorRecord | None:
        records = self.read_all(environment_slug)
        return records[-1] if records else None
