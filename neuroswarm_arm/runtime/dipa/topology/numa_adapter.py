"""DIPA NUMA adapter — delegates to HAOE sysfs topology (not hardcoded [0])."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.haoe.topology.cpu_topology import read_numa_topology
from neuroswarm_arm.runtime.haoe.topology.topology_service import TopologyService


class NumaAdapter:
    """NUMA node lists for DIPA routing / placement.

    Uses HAOE TopologyService when provided; otherwise reads
    ``/sys/devices/system/node`` (same source as HAOE). On GCP Axion C4A
    (single UMA domain) this returns ``[0]``.
    """

    def __init__(self, topology: TopologyService | Any | None = None) -> None:
        self._topo = topology

    def nodes(self) -> list[int]:
        if self._topo is not None:
            fn = getattr(self._topo, "numa_nodes", None)
            if callable(fn):
                try:
                    return [int(n) for n in fn()]
                except Exception:  # noqa: BLE001
                    pass
            snap = getattr(self._topo, "snapshot", None)
            if snap is not None:
                numa = getattr(getattr(snap, "topology", None), "numa_nodes", None)
                if isinstance(numa, dict) and numa:
                    return sorted(int(k) for k in numa.keys())
        return sorted(read_numa_topology().keys()) or [0]

    def preferred(self) -> int:
        nodes = self.nodes()
        return int(nodes[0]) if nodes else 0

    def cores_for_node(self, node: int) -> list[int]:
        if self._topo is not None:
            fn = getattr(self._topo, "cores_for_node", None)
            if callable(fn):
                try:
                    return [int(c) for c in fn(int(node))]
                except Exception:  # noqa: BLE001
                    pass
        return list(read_numa_topology().get(int(node), []))
