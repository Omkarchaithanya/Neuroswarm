"""NUMA placement policy and local RAM allocator."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from ..interfaces.allocator import IKVAllocator
from ..utils.logging import get_logger

logger = get_logger("neuroswarm.kv.allocator")


def detect_numa_nodes() -> list[int]:
    """Detect NUMA nodes; fall back to [0] on Axion / Windows / missing sysfs."""
    sysfs = Path("/sys/devices/system/node")
    if not sysfs.exists():
        return [0]
    nodes: list[int] = []
    for child in sorted(sysfs.iterdir()):
        name = child.name
        if name.startswith("node") and name[4:].isdigit():
            nodes.append(int(name[4:]))
    return nodes or [0]


class NUMAPlacementPolicy:
    """Prefer local-node allocation; degrade gracefully on single-socket Axion."""

    def __init__(self, preferred_node: int = -1) -> None:
        self.nodes = detect_numa_nodes()
        if preferred_node >= 0 and preferred_node in self.nodes:
            self.preferred = preferred_node
        else:
            self.preferred = self.nodes[0]
        self.multi_node = len(self.nodes) > 1
        if not self.multi_node:
            logger.info("numa_fallback single_node=%s", self.preferred)

    def choose_node(self, hint: int | None = None) -> int:
        if hint is not None and hint in self.nodes:
            return hint
        return self.preferred

    def affinity_cores(self, node: int | None = None) -> list[int]:
        node = self.preferred if node is None else node
        cpulist = Path(f"/sys/devices/system/node/node{node}/cpulist")
        if not cpulist.exists():
            return list(range(8))
        text = cpulist.read_text(encoding="utf-8").strip()
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
        return cores or list(range(8))


class LocalRAMAllocator(IKVAllocator):
    """Process-local byte allocator with budget tracking (NUMA-tagged)."""

    def __init__(
        self,
        *,
        node_id: int = 0,
        budget_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        self._node_id = node_id
        self._budget = max(1, int(budget_bytes))
        self._used = 0
        self._lock = RLock()
        self._live: dict[int, bytearray] = {}

    @property
    def node_id(self) -> int:
        return self._node_id

    def allocate(self, size: int) -> memoryview:
        size = max(0, int(size))
        with self._lock:
            if self._used + size > self._budget:
                raise MemoryError(
                    f"NUMA node {self._node_id} budget exceeded "
                    f"({self._used + size} > {self._budget})"
                )
            buf = bytearray(size)
            self._live[id(buf)] = buf
            self._used += size
            return memoryview(buf)

    def free(self, buf: memoryview) -> None:
        with self._lock:
            obj = buf.obj if hasattr(buf, "obj") else None
            key = id(obj) if obj is not None else None
            if key is not None and key in self._live:
                size = len(self._live.pop(key))
                self._used = max(0, self._used - size)
            try:
                buf.release()
            except Exception:
                pass

    def available_bytes(self) -> int:
        with self._lock:
            return max(0, self._budget - self._used)

    def used_bytes(self) -> int:
        with self._lock:
            return self._used
