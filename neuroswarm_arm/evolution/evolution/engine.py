"""Policy lineage / evolution engine — OKF + in-memory graph."""

from __future__ import annotations

import threading
from pathlib import Path

from neuroswarm_arm.evolution.interfaces.evolution import EvolutionEngine, PolicyLineage
from neuroswarm_arm.evolution.knowledge.engine import OKFKnowledgeStore
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class LineageEvolutionEngine(EvolutionEngine):
    def __init__(self, *, okf: OKFKnowledgeStore | None = None) -> None:
        self.okf = okf
        self._lock = threading.RLock()
        self._lineage: dict[str, list[PolicyLineage]] = {}
        self._graph: dict[str, list[str]] = {}

    def record(self, policy: RuntimePolicy, *, okf_path: str | None = None) -> PolicyLineage:
        path = okf_path
        if path is None and self.okf is not None:
            try:
                written = self.okf.write_policy(policy)
                path = str(written)
            except Exception:
                path = None
        entry = PolicyLineage(
            policy_id=policy.id,
            version=policy.version,
            parent_id=policy.parent_policy_id,
            content_hash=policy.content_hash,
            okf_path=path,
            metadata={"expected_reward": policy.expected_reward},
        )
        with self._lock:
            self._lineage.setdefault(policy.id, []).append(entry)
            if policy.parent_policy_id:
                self._graph.setdefault(policy.parent_policy_id, []).append(policy.id)
            else:
                self._graph.setdefault(policy.id, [])
        return entry

    def lineage(self, policy_id: str) -> list[PolicyLineage]:
        with self._lock:
            return list(self._lineage.get(policy_id, []))

    def graph(self) -> dict[str, list[str]]:
        with self._lock:
            return {k: list(v) for k, v in self._graph.items()}
