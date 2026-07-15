"""NUMA adapter — soft locality hints; never requires multi-node hardware."""

from __future__ import annotations

from dataclasses import dataclass

from .topology_service import TopologyService


@dataclass(slots=True)
class NumaPlacement:
    node: int
    cores: list[int]
    multi_node: bool


class NumaAdapter:
    """Translate preferred node / locality tag into core lists.

    On GCP Axion (single socket, no user-space NUMA guarantees) this returns
    node 0 with all cores. Future multi-node Neoverse boxes plug in via the
    same API without scheduler changes.
    """

    def __init__(self, topology: TopologyService) -> None:
        self._topo = topology

    def place(self, preferred_node: int | None = None) -> NumaPlacement:
        nodes = self._topo.numa_nodes()
        multi = len(nodes) > 1
        if preferred_node is not None and preferred_node in nodes:
            node = preferred_node
        else:
            node = nodes[0] if nodes else 0
        cores = self._topo.cores_for_node(node) or self._topo.core_ids()
        return NumaPlacement(node=node, cores=cores, multi_node=multi)
