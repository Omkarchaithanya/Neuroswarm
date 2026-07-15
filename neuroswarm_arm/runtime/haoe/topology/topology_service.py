"""TopologyService — stable API over HardwareDetector snapshot."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces import ITopologyService
from ..interfaces.types import FeatureStatus
from .hardware_detector import HardwareDetector, HardwareSnapshot


class TopologyService(ITopologyService):
    def __init__(self, snapshot: HardwareSnapshot | None = None, **detector_kw: Any) -> None:
        if snapshot is None:
            snapshot = HardwareDetector(**detector_kw).detect()
        self._snap = snapshot

    @property
    def snapshot(self) -> HardwareSnapshot:
        return self._snap

    def refresh(self, **detector_kw: Any) -> HardwareSnapshot:
        self._snap = HardwareDetector(**detector_kw).detect()
        return self._snap

    def cpu_count(self) -> int:
        return len(self._snap.topology.logical_cpus) or 1

    def core_ids(self) -> list[int]:
        return list(self._snap.topology.logical_cpus)

    def fast_cores(self) -> list[int]:
        return list(self._snap.topology.fast_cores)

    def efficiency_cores(self) -> list[int]:
        return list(self._snap.topology.efficiency_cores)

    def numa_nodes(self) -> list[int]:
        return sorted(self._snap.topology.numa_nodes.keys())

    def cores_for_node(self, node: int) -> list[int]:
        return list(self._snap.topology.numa_nodes.get(node, []))

    def feature(self, name: str) -> FeatureStatus:
        return self._snap.features.status(name)

    def features(self) -> Mapping[str, FeatureStatus]:
        return dict(self._snap.features.features)

    def cache_hierarchy(self) -> Mapping[str, Any]:
        return {
            "levels": [
                {
                    "level": c.level,
                    "size_bytes": c.size_bytes,
                    "type": c.type,
                    "shared_cpu_list": list(c.shared_cpu_list),
                }
                for c in self._snap.topology.caches
            ]
        }
