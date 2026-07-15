"""
CandidatePool — append-only GEPA candidate store.

Official concept: candidate pool maintained across reflective evolution
iterations (never overwrite; lineage preserved).

ArmCascade/AROP: stores TextCandidate objects for Pareto + approval.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from neuroswarm_arm.evolution.reflection.gepa.candidate.models import TextCandidate


class CandidatePool:
    """Append-only pool. Do not overwrite candidates — register new versions."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, TextCandidate] = {}
        self._order: list[str] = []
        self._store_path = store_path
        if store_path and store_path.exists():
            self._load(store_path)

    def add(self, candidate: TextCandidate) -> TextCandidate:
        with self._lock:
            if candidate.id in self._by_id:
                # Never overwrite — require new id for new content
                existing = self._by_id[candidate.id]
                if existing.content_hash != candidate.content_hash:
                    raise ValueError(
                        f"refusing overwrite of candidate {candidate.id}; "
                        "create a new TextCandidate id instead"
                    )
                return existing
            self._by_id[candidate.id] = candidate
            self._order.append(candidate.id)
            self._persist()
            return candidate

    def get(self, candidate_id: str) -> TextCandidate | None:
        with self._lock:
            return self._by_id.get(candidate_id)

    def replace_same_id(self, candidate: TextCandidate) -> TextCandidate:
        """Allow metadata/score/approval updates on same id (not component overwrite)."""
        with self._lock:
            prev = self._by_id.get(candidate.id)
            if prev is not None and prev.content_hash != candidate.content_hash:
                raise ValueError("cannot change components via replace_same_id")
            self._by_id[candidate.id] = candidate
            if candidate.id not in self._order:
                self._order.append(candidate.id)
            self._persist()
            return candidate

    def all(self) -> list[TextCandidate]:
        with self._lock:
            return [self._by_id[i] for i in self._order if i in self._by_id]

    def lineage(self, candidate_id: str) -> list[TextCandidate]:
        with self._lock:
            out: list[TextCandidate] = []
            seen: set[str] = set()
            stack = [candidate_id]
            while stack:
                cid = stack.pop()
                if cid in seen:
                    continue
                seen.add(cid)
                c = self._by_id.get(cid)
                if c is None:
                    continue
                out.append(c)
                stack.extend(c.parent_ids)
            return out

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"n_candidates": len(self._by_id), "ids": list(self._order[-20:])}

    def _persist(self) -> None:
        if not self._store_path:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"candidates": [c.to_dict() for c in self.all()]}
        self._store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        from datetime import datetime

        for raw in data.get("candidates", []):
            try:
                created = datetime.fromisoformat(raw["created_at"])
            except Exception:
                created = datetime.utcnow()
            c = TextCandidate(
                id=raw["id"],
                version=raw.get("version", "v0"),
                components=dict(raw.get("components") or {}),
                created_at=created,
                parent_ids=tuple(raw.get("parent_ids") or []),
                content_hash=raw.get("content_hash", ""),
                scores=dict(raw.get("scores") or {}),
                per_task_scores=dict(raw.get("per_task_scores") or {}),
                metadata=dict(raw.get("metadata") or {}),
                approved=bool(raw.get("approved", False)),
                deployed=bool(raw.get("deployed", False)),
            )
            self._by_id[c.id] = c
            self._order.append(c.id)
