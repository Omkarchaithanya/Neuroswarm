"""Recovery engine — rebuild sessions, tables, refcounts, storage locations."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..block.models import SessionBlockTable
from ..block.tables import LogicalBlockTable, PhysicalBlockTable
from ..interfaces.types import PhysicalBlockRecord
from ..utils.hashing import content_hash
from ..utils.logging import get_logger

logger = get_logger("neuroswarm.kv.recovery")


@dataclass
class RecoveryResult:
    sessions_restored: int
    blocks_restored: int
    corrupt_sessions: list[str]
    ok: bool


class RecoveryEngine:
    """Recover runtime state from checkpoint metadata + journal."""

    def __init__(self, journal_dir: Path) -> None:
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    def journal_path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_")
        return self.journal_dir / f"{safe}.wal.json"

    def write_journal(self, session_id: str, record: dict[str, Any]) -> None:
        path = self.journal_path(session_id)
        payload = {"ts": time.time(), "session_id": session_id, **record}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def read_journal(self, session_id: str) -> dict[str, Any] | None:
        path = self.journal_path(session_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def validate_payloads(
        self,
        meta: dict[str, Any],
        payloads: dict[str, bytes],
    ) -> list[str]:
        """Return list of corrupt block ids (hash mismatch)."""
        expected = dict(meta.get("content_hashes", {}))
        corrupt: list[str] = []
        for block_id, data in payloads.items():
            want = expected.get(block_id)
            if want and content_hash(data) != want:
                corrupt.append(block_id)
        return corrupt

    def rebuild_tables(
        self,
        meta: dict[str, Any],
        *,
        physical: PhysicalBlockTable,
    ) -> tuple[SessionBlockTable, LogicalBlockTable]:
        session = SessionBlockTable.from_dict(meta["session"])
        logical = LogicalBlockTable(session.session_id)
        logical.load_dict(meta.get("logical_map", {}))
        records = [PhysicalBlockRecord.from_dict(r) for r in meta.get("physical_records", [])]
        # Merge into global physical table without wiping unrelated sessions
        for rec in records:
            existing = physical.get(rec.physical_id)
            if existing is None:
                physical.register(rec)
            else:
                physical.acquire(rec.physical_id)
        return session, logical

    def recover_from_checkpoint(
        self,
        session_id: str,
        meta: dict[str, Any],
        payloads: dict[str, bytes],
        *,
        physical: PhysicalBlockTable,
    ) -> RecoveryResult:
        corrupt = self.validate_payloads(meta, payloads)
        if corrupt:
            logger.error("corrupt_session session_id=%s blocks=%s", session_id, corrupt)
            return RecoveryResult(
                sessions_restored=0,
                blocks_restored=0,
                corrupt_sessions=[session_id],
                ok=False,
            )
        session, _logical = self.rebuild_tables(meta, physical=physical)
        self.write_journal(
            session_id,
            {"event": "recovered", "blocks": len(session.blocks), "ok": True},
        )
        return RecoveryResult(
            sessions_restored=1,
            blocks_restored=len(session.blocks),
            corrupt_sessions=[],
            ok=True,
        )
