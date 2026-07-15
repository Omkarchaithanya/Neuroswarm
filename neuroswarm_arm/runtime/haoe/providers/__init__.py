"""Provider implementations — pluggable HAL for current Axion + future ARM."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

from ..interfaces import (
    IAffinityProvider,
    ICPUProvider,
    IKVPressureProvider,
    IMemoryProvider,
    ISchedulingProvider,
)
from ..interfaces.types import PoolKind
from ..runtime.runtime_config import HAOERuntimeConfig
from ..topology.topology_service import TopologyService


class SystemCPUProvider(ICPUProvider):
    def __init__(self, topology: TopologyService) -> None:
        self._topo = topology

    def core_ids(self) -> list[int]:
        return self._topo.core_ids()

    def logical_count(self) -> int:
        return self._topo.cpu_count()


class SystemTopologyProvider:
    """Facade alias used by registry — wraps TopologyService."""

    def __init__(self, topology: TopologyService) -> None:
        self.topology = topology


class SchedSetAffinityProvider(IAffinityProvider):
    """Linux os.sched_setaffinity; no-op elsewhere (Windows / restricted containers)."""

    def bind(self, cores: Sequence[int]) -> bool:
        if not cores:
            return False
        try:
            os.sched_setaffinity(0, set(int(c) for c in cores))
            return True
        except (AttributeError, OSError, ValueError):
            return False

    def unbind(self) -> bool:
        try:
            # Reset to all online CPUs when possible.
            online = Path("/sys/devices/system/cpu/online")
            if online.exists():
                from ..topology.cpu_topology import parse_cpu_list

                cores = parse_cpu_list(online.read_text(encoding="utf-8").strip())
                os.sched_setaffinity(0, set(cores))
                return True
            count = os.cpu_count() or 1
            os.sched_setaffinity(0, set(range(count)))
            return True
        except (AttributeError, OSError, ValueError):
            return False

    def current(self) -> list[int]:
        try:
            return sorted(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            return list(range(os.cpu_count() or 1))


class NoOpAffinityProvider(IAffinityProvider):
    def bind(self, cores: Sequence[int]) -> bool:
        return False

    def unbind(self) -> bool:
        return False

    def current(self) -> list[int]:
        return list(range(os.cpu_count() or 1))


class SystemMemoryProvider(IMemoryProvider):
    """RAM pressure via psutil when available; otherwise conservative defaults."""

    def name(self) -> str:
        return "system_ram"

    def available_bytes(self) -> int:
        try:
            import psutil

            return int(psutil.virtual_memory().available)
        except Exception:
            return 0

    def pressure(self) -> float:
        try:
            import psutil

            return float(psutil.virtual_memory().percent) / 100.0
        except Exception:
            return 0.0


class FutureMTEMemoryProvider(IMemoryProvider):
    """Stub for future Memory Tagging Extension — not available on Axion today."""

    def name(self) -> str:
        return "mte_future"

    def available_bytes(self) -> int:
        return 0

    def pressure(self) -> float:
        return 0.0


class CallableKVPressureProvider(IKVPressureProvider):
    def __init__(self, fn: object | None = None) -> None:
        self._fn = fn

    def pressure_snapshot(self) -> Mapping[str, object]:
        if self._fn is None:
            return {"pressure": 0.0}
        snap = self._fn() if callable(self._fn) else self._fn
        if hasattr(snap, "__dict__") and not isinstance(snap, Mapping):
            # Support PressureSnapshot dataclasses from KV without importing them.
            data = {}
            for key in (
                "pressure",
                "hit_rate",
                "ram_used_bytes",
                "ram_budget_bytes",
                "pending_migrations",
            ):
                if hasattr(snap, key):
                    data[key] = getattr(snap, key)
            return data
        if isinstance(snap, Mapping):
            return dict(snap)
        return {"pressure": float(snap)}


class ConfigSchedulingProvider(ISchedulingProvider):
    def __init__(self, config: HAOERuntimeConfig) -> None:
        self._config = config

    def pool_size(self, pool: PoolKind) -> int:
        return self._config.pool_size(pool)

    def steal_enabled(self) -> bool:
        return bool(self._config.work_stealing)


def build_affinity_provider(*, enabled: bool = True) -> IAffinityProvider:
    if not enabled:
        return NoOpAffinityProvider()
    # Probe once.
    probe = SchedSetAffinityProvider()
    try:
        cur = probe.current()
        if cur and probe.bind(cur[:1] or cur):
            probe.unbind()
            return probe
    except Exception:
        pass
    return NoOpAffinityProvider()
