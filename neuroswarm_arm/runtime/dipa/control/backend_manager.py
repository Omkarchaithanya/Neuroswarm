"""BackendManager — registry lifecycle + capability aggregation."""

from __future__ import annotations

import threading
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.backends.registry import BackendRegistry
from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import HealthState, HealthStatus


class BackendManager:
    def __init__(self, registry: BackendRegistry | None = None) -> None:
        self._lock = threading.RLock()
        self.registry = registry or BackendRegistry()
        self._started = False

    def register(self, backend: InferenceBackend) -> None:
        with self._lock:
            self.registry.register(backend)

    def get(self, name: str) -> InferenceBackend | None:
        return self.registry.get(name)

    def list(self) -> list[str]:
        return self.registry.list()

    def capabilities(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name in self.registry.list():
            be = self.registry.get(name)
            if be is None:
                continue
            caps = be.capabilities
            out[name] = {
                "streaming": caps.streaming,
                "batching": caps.batching,
                "continuous_batching": caps.continuous_batching,
                "prefill_decode_split": caps.prefill_decode_split,
                "prefix_caching": getattr(caps, "prefix_caching", False),
                "speculation": caps.speculation,
                "kleidiai": caps.kleidiai,
                "tokenize": getattr(caps, "tokenize", False),
                "device_classes": [d.value for d in caps.device_classes],
            }
        return out

    async def health_all(self) -> dict[str, HealthStatus]:
        return await self.registry.health_all()

    def start(self) -> None:
        with self._lock:
            self._started = True

    def stop(self) -> None:
        with self._lock:
            for name in list(self.registry.list()):
                be = self.registry.get(name)
                stop = getattr(be, "stop", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        pass
            self._started = False

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "started": self._started,
            "backends": self.list(),
            "capabilities": self.capabilities(),
        }

    def overall_health(self, statuses: Mapping[str, HealthStatus]) -> HealthState:
        if not statuses:
            return HealthState.UNKNOWN
        states = [s.state for s in statuses.values()]
        if all(s == HealthState.HEALTHY for s in states):
            return HealthState.HEALTHY
        if any(s == HealthState.HEALTHY for s in states):
            return HealthState.DEGRADED
        return HealthState.UNHEALTHY
