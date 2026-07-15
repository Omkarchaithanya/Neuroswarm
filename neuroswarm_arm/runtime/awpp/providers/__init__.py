"""Hardware / future-feature providers for AWPP on GCP Axion."""

from __future__ import annotations

import os
from typing import Sequence

from ..interfaces import FeatureStatus, ICXLProvider, IMTEProvider


class UnavailableMTEProvider(IMTEProvider):
    """Axion public SKUs do not expose MTE — software path only."""

    def status(self) -> FeatureStatus:
        return FeatureStatus.UNAVAILABLE

    def tag_pages(self, pages: list[str], agent_id: str) -> bool:
        return False


class UnavailableCXLProvider(ICXLProvider):
    """Axion public SKUs do not expose CXL — use RAM/mmap/Redis instead."""

    def status(self) -> FeatureStatus:
        return FeatureStatus.UNAVAILABLE

    def prefetch(self, keys: list[str]) -> int:
        return 0


class NumaProvider:
    """Best-effort NUMA detection for warmer locality."""

    def __init__(self, preferred_node: int | None = None) -> None:
        self.preferred_node = preferred_node
        self._nodes = self._detect_nodes()

    def _detect_nodes(self) -> list[int]:
        try:
            path = "/sys/devices/system/node"
            if os.path.isdir(path):
                nodes = []
                for name in os.listdir(path):
                    if name.startswith("node") and name[4:].isdigit():
                        nodes.append(int(name[4:]))
                return sorted(nodes) or [0]
        except Exception:
            pass
        return [0]

    def nodes(self) -> list[int]:
        return list(self._nodes)

    def pick(self) -> int:
        if self.preferred_node is not None and self.preferred_node in self._nodes:
            return self.preferred_node
        return self._nodes[0] if self._nodes else 0


class AffinityProvider:
    """Thread affinity helper — best-effort on Axion/Windows."""

    def __init__(self, cores: Sequence[int] | None = None, *, enabled: bool = True) -> None:
        self.cores = list(cores or [])
        self.enabled = enabled

    def bind_current(self) -> bool:
        if not self.enabled or not self.cores:
            return False
        try:
            os.sched_setaffinity(0, set(self.cores[: max(1, len(self.cores) // 4)]))
            return True
        except Exception:
            return False


class HugePageHint:
    """Advise huge-page friendliness; no hard dependency on hugetlbfs."""

    def __init__(self) -> None:
        self.available = self._probe()

    def _probe(self) -> bool:
        try:
            return os.path.exists("/sys/kernel/mm/hugepages")
        except Exception:
            return False

    def status(self) -> FeatureStatus:
        return FeatureStatus.AVAILABLE if self.available else FeatureStatus.UNAVAILABLE
