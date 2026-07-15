"""CPU topology models — core lists, cache hierarchy, NUMA nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CacheLevel:
    level: int
    size_bytes: int = 0
    type: str = "unified"
    shared_cpu_list: list[int] = field(default_factory=list)


@dataclass(slots=True)
class CPUTopology:
    """Logical view of the machine. Homogeneous Axion = one node, N cores."""

    arch: str = ""
    logical_cpus: list[int] = field(default_factory=list)
    numa_nodes: dict[int, list[int]] = field(default_factory=dict)
    caches: list[CacheLevel] = field(default_factory=list)
    fast_cores: list[int] = field(default_factory=list)
    efficiency_cores: list[int] = field(default_factory=list)

    def all_cores(self) -> list[int]:
        return list(self.logical_cpus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arch": self.arch,
            "logical_cpus": list(self.logical_cpus),
            "numa_nodes": {str(k): v for k, v in self.numa_nodes.items()},
            "fast_cores": list(self.fast_cores),
            "efficiency_cores": list(self.efficiency_cores),
            "caches": [
                {
                    "level": c.level,
                    "size_bytes": c.size_bytes,
                    "type": c.type,
                    "shared_cpu_list": list(c.shared_cpu_list),
                }
                for c in self.caches
            ],
        }


def parse_cpu_list(text: str) -> list[int]:
    """Parse Linux cpulist format: '0-3,8,10-11'."""
    cores: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            cores.extend(range(int(a), int(b) + 1))
        else:
            cores.append(int(part))
    return cores


def read_online_cpus() -> list[int]:
    path = Path("/sys/devices/system/cpu/online")
    if path.exists():
        try:
            return parse_cpu_list(path.read_text(encoding="utf-8").strip())
        except OSError:
            pass
    import os

    return list(range(os.cpu_count() or 1))


def read_numa_topology() -> dict[int, list[int]]:
    sysfs = Path("/sys/devices/system/node")
    if not sysfs.exists():
        return {0: read_online_cpus()}
    nodes: dict[int, list[int]] = {}
    try:
        for child in sorted(sysfs.iterdir()):
            name = child.name
            if not (name.startswith("node") and name[4:].isdigit()):
                continue
            node_id = int(name[4:])
            cpulist = child / "cpulist"
            if cpulist.exists():
                nodes[node_id] = parse_cpu_list(
                    cpulist.read_text(encoding="utf-8").strip()
                )
            else:
                nodes[node_id] = []
    except OSError:
        return {0: read_online_cpus()}
    return nodes or {0: read_online_cpus()}


def read_cache_hierarchy(cpu: int = 0) -> list[CacheLevel]:
    base = Path(f"/sys/devices/system/cpu/cpu{cpu}/cache")
    if not base.exists():
        return []
    caches: list[CacheLevel] = []
    try:
        for index_dir in sorted(base.iterdir()):
            if not index_dir.name.startswith("index"):
                continue
            try:
                level = int((index_dir / "level").read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            size_bytes = 0
            size_path = index_dir / "size"
            if size_path.exists():
                raw = size_path.read_text(encoding="utf-8").strip().upper()
                try:
                    if raw.endswith("K"):
                        size_bytes = int(raw[:-1]) * 1024
                    elif raw.endswith("M"):
                        size_bytes = int(raw[:-1]) * 1024 * 1024
                    else:
                        size_bytes = int(raw)
                except ValueError:
                    size_bytes = 0
            ctype = "unified"
            type_path = index_dir / "type"
            if type_path.exists():
                ctype = type_path.read_text(encoding="utf-8").strip().lower()
            shared: list[int] = []
            shared_path = index_dir / "shared_cpu_list"
            if shared_path.exists():
                shared = parse_cpu_list(
                    shared_path.read_text(encoding="utf-8").strip()
                )
            caches.append(
                CacheLevel(
                    level=level,
                    size_bytes=size_bytes,
                    type=ctype,
                    shared_cpu_list=shared,
                )
            )
    except OSError:
        return caches
    return caches
