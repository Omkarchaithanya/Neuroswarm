"""NUMA placement — sysfs-backed; single-node Axion stays on node 0."""

from __future__ import annotations

from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.topology.numa_adapter import NumaAdapter

from ..interfaces.types import ExecutionPlan


class NumaRouter:
    """Return NUMA node for a plan.

    On single-node hosts (GCP C4A / Axion UMA) always returns 0.
    On multi-node hosts, uses plan.numa_node when set, else preferred node.
    ``numa_fallback_single_node`` only forces node 0 when topology has <=1 node
    or detector fails — it does not hide real multi-node topology.
    """

    def __init__(
        self,
        hardware_cfg: Mapping[str, Any] | None = None,
        detector: Any | None = None,
        adapter: NumaAdapter | None = None,
    ) -> None:
        self.hardware_cfg = dict(hardware_cfg or {})
        self.detector = detector
        self.adapter = adapter or NumaAdapter(topology=detector)
        self.fallback_single_node = bool(
            self.hardware_cfg.get("numa_fallback_single_node", True)
        )

    def node_for(self, plan: ExecutionPlan | None = None) -> int:
        nodes = self._nodes()
        if len(nodes) <= 1:
            node = int(nodes[0]) if nodes else 0
            if plan is not None:
                plan.numa_node = node
            return node

        if plan is not None and getattr(plan, "numa_node", None) is not None:
            preferred = int(plan.numa_node)
            if preferred in nodes:
                return preferred

        node = int(self.adapter.preferred())
        if plan is not None:
            plan.numa_node = node
        return node

    def _nodes(self) -> list[int]:
        if self.detector is not None:
            fn = getattr(self.detector, "numa_nodes", None)
            if callable(fn):
                try:
                    found = [int(n) for n in fn()]
                    if found:
                        return found
                except Exception:  # noqa: BLE001
                    pass
        try:
            return self.adapter.nodes()
        except Exception:  # noqa: BLE001
            return [0] if self.fallback_single_node else [0]
