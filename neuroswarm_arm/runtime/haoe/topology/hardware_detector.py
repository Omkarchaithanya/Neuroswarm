"""Hardware detector — composes FeatureDetector + CPUTopology."""

from __future__ import annotations

import platform
from dataclasses import dataclass

from .cpu_topology import (
    CPUTopology,
    read_cache_hierarchy,
    read_numa_topology,
    read_online_cpus,
)
from .feature_detector import FeatureDetector, FeatureSet


@dataclass(slots=True)
class HardwareSnapshot:
    topology: CPUTopology
    features: FeatureSet

    def to_dict(self) -> dict:
        return {
            "topology": self.topology.to_dict(),
            "features": self.features.to_dict(),
            "arch": self.features.arch or self.topology.arch,
        }


class HardwareDetector:
    """Single entry point for platform discovery."""

    def __init__(
        self,
        *,
        fast_core_fraction: float = 0.5,
        override_cores: list[int] | None = None,
    ) -> None:
        self._fast_frac = min(1.0, max(0.1, fast_core_fraction))
        self._override_cores = override_cores
        self._features = FeatureDetector()

    def detect(self) -> HardwareSnapshot:
        features = self._features.detect()
        cores = list(self._override_cores) if self._override_cores else read_online_cpus()
        numa = read_numa_topology()
        # If override provided, collapse NUMA map to those cores on node 0 when
        # sysfs is missing/mismatched (Windows / containers).
        if self._override_cores is not None:
            known = set(cores)
            filtered = {
                nid: [c for c in clist if c in known] for nid, clist in numa.items()
            }
            filtered = {k: v for k, v in filtered.items() if v}
            numa = filtered or {0: cores}

        n_fast = max(1, int(len(cores) * self._fast_frac))
        fast = cores[:n_fast]
        slow = cores[n_fast:] or cores[:]

        topo = CPUTopology(
            arch=platform.machine(),
            logical_cpus=cores,
            numa_nodes=numa,
            caches=read_cache_hierarchy(cores[0] if cores else 0),
            fast_cores=fast,
            efficiency_cores=slow,
        )
        return HardwareSnapshot(topology=topo, features=features)
