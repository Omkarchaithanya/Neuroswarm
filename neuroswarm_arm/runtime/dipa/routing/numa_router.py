"""NUMA placement — Axion fallback always node 0."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.types import ExecutionPlan


class NumaRouter:
    """Return NUMA node for a plan; single-node Axion fallback is always 0."""

    def __init__(
        self,
        hardware_cfg: Mapping[str, Any] | None = None,
        detector: Any | None = None,
    ) -> None:
        self.hardware_cfg = dict(hardware_cfg or {})
        self.detector = detector
        self.fallback_single_node = bool(
            self.hardware_cfg.get("numa_fallback_single_node", True)
        )

    def node_for(self, plan: ExecutionPlan | None = None) -> int:
        if self.fallback_single_node:
            node = 0
            if plan is not None:
                plan.numa_node = node
            return node

        nodes = self._nodes()
        node = int(nodes[0]) if nodes else 0
        if plan is not None:
            plan.numa_node = node
        return node

    def _nodes(self) -> list[int]:
        if self.detector is not None:
            fn = getattr(self.detector, "numa_nodes", None)
            if callable(fn):
                try:
                    return [int(n) for n in fn()]
                except Exception:  # noqa: BLE001
                    return [0]
        return [0]
