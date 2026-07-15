"""Context Versioning — hash, diff, rollback, lineage, provenance."""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot, ContextVersion


class ContextVersioning:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: dict[str, ContextSnapshot] = {}
        self._order: list[str] = []

    def stamp(self, snapshot: ContextSnapshot) -> ContextSnapshot:
        content = snapshot.prompt or ""
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        parent = self._order[-1] if self._order else ""
        lineage = list(self._history[parent].version.lineage) if parent and parent in self._history else []
        ver = ContextVersion(
            content_hash=h,
            parent_id=parent,
            lineage=lineage + ([parent] if parent else []),
            build_history=[
                f"plan={snapshot.plan_id}",
                f"sections={len(snapshot.sections)}",
                f"tokens={snapshot.token_count}",
            ],
            metadata={"request_id": snapshot.request_id},
        )
        if parent:
            ver.lineage = lineage + [parent]
        snapshot.version = ver
        with self._lock:
            self._history[ver.version_id] = snapshot
            self._order.append(ver.version_id)
            if len(self._order) > 200:
                old = self._order.pop(0)
                self._history.pop(old, None)
        return snapshot

    def diff(self, a: ContextSnapshot, b: ContextSnapshot) -> dict[str, Any]:
        a_lines = set((a.prompt or "").splitlines())
        b_lines = set((b.prompt or "").splitlines())
        return {
            "added": sorted(b_lines - a_lines)[:50],
            "removed": sorted(a_lines - b_lines)[:50],
            "a_hash": a.version.content_hash,
            "b_hash": b.version.content_hash,
            "a_tokens": a.token_count,
            "b_tokens": b.token_count,
        }

    def rollback(self, version_id: str) -> ContextSnapshot | None:
        with self._lock:
            return self._history.get(version_id)

    def get(self, version_id: str) -> ContextSnapshot | None:
        return self.rollback(version_id)

    def export_provenance(self, snapshot: ContextSnapshot) -> str:
        payload = {
            "version_id": snapshot.version.version_id,
            "content_hash": snapshot.version.content_hash,
            "lineage": snapshot.version.lineage,
            "provenance": [
                {"kind": p.kind, "ref_id": p.ref_id, "path": p.path, "score": p.score}
                for p in snapshot.provenance
            ],
            "build_history": snapshot.version.build_history,
        }
        return json.dumps(payload, indent=2)
