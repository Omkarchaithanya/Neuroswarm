"""HardwareTopology HAL — NUMA if available, local otherwise. Never hardcode NUMA."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CacheLevel:
    level: int
    size_kb: int = 0
    shared: bool = False


@dataclass(slots=True)
class PlacementHint:
    numa_node: int | None = None
    local_only: bool = True
    reason: str = "fallback_local"


@dataclass(slots=True)
class TopologySnapshot:
    arch: str = ""
    cpu_count: int = 0
    numa_nodes: list[int] = field(default_factory=list)
    cache_hierarchy: list[CacheLevel] = field(default_factory=list)
    huge_pages_available: bool = False
    cxl_hint: bool = False  # future
    metadata: dict[str, Any] = field(default_factory=dict)


class HardwareTopology:
    """Portable topology discovery. ARM Neoverse first; no hardcoded node counts."""

    def __init__(self) -> None:
        self._snap: TopologySnapshot | None = None

    def discover(self) -> TopologySnapshot:
        if self._snap is not None:
            return self._snap
        snap = TopologySnapshot(
            arch=platform.machine(),
            cpu_count=os.cpu_count() or 1,
            numa_nodes=self._discover_numa() or [],
            cache_hierarchy=self._discover_cache(),
            huge_pages_available=self._huge_pages(),
            cxl_hint=False,
            metadata={"platform": platform.platform()},
        )
        self._snap = snap
        return snap

    def numa_nodes(self) -> list[int] | None:
        nodes = self.discover().numa_nodes
        return nodes if nodes else None

    def cache_hierarchy(self) -> list[CacheLevel]:
        return list(self.discover().cache_hierarchy)

    def prefer_local(self, size_bytes: int = 0) -> PlacementHint:
        # ARM: prefer local allocation; use NUMA only when discovered.
        nodes = self.numa_nodes()
        if nodes:
            # Pick first online node — callers may override with affinity.
            return PlacementHint(numa_node=nodes[0], local_only=True, reason="numa_discovered")
        return PlacementHint(numa_node=None, local_only=True, reason="fallback_local")

    def pin_workers(self, worker_count: int | None = None) -> int:
        """Best-effort worker count; affinity pinning is OS-specific."""
        cpus = self.discover().cpu_count
        if worker_count is None:
            worker_count = max(1, min(cpus, 8))
        return worker_count

    def _discover_numa(self) -> list[int] | None:
        # Linux sysfs — never assume node count.
        base = Path("/sys/devices/system/node")
        if not base.is_dir():
            return None
        nodes: list[int] = []
        for p in sorted(base.glob("node[0-9]*")):
            try:
                nodes.append(int(p.name.replace("node", "")))
            except ValueError:
                continue
        return nodes or None

    def _discover_cache(self) -> list[CacheLevel]:
        levels: list[CacheLevel] = []
        cpu0 = Path("/sys/devices/system/cpu/cpu0/cache")
        if not cpu0.is_dir():
            return levels
        for idx in sorted(cpu0.glob("index*")):
            try:
                level = int((idx / "level").read_text().strip())
                size_raw = (idx / "size").read_text().strip().upper()
                size_kb = 0
                if size_raw.endswith("K"):
                    size_kb = int(size_raw[:-1])
                elif size_raw.endswith("M"):
                    size_kb = int(size_raw[:-1]) * 1024
                shared = "Shared" in (idx / "type").read_text() if (idx / "type").exists() else False
                levels.append(CacheLevel(level=level, size_kb=size_kb, shared=shared))
            except Exception:
                continue
        return levels

    def _huge_pages(self) -> bool:
        p = Path("/sys/kernel/mm/hugepages")
        return p.is_dir()
