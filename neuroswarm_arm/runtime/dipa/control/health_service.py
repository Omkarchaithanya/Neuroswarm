"""HealthService — aggregate readiness / liveness."""

from __future__ import annotations

from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.types import HealthState

from .backend_manager import BackendManager
from .lifecycle_manager import LifecycleManager
from .metrics_collector import MetricsCollector


class HealthService:
    def __init__(
        self,
        backends: BackendManager,
        lifecycle: LifecycleManager,
        metrics: MetricsCollector | None = None,
        *,
        config: Any | None = None,
        backends_registry: Any | None = None,
    ) -> None:
        self.backends = backends
        self.lifecycle = lifecycle
        self.metrics = metrics
        self.config = config
        self.backends_registry = backends_registry

    def liveness(self) -> Mapping[str, Any]:
        phase = self.lifecycle.phase()
        alive = phase.value not in {"stopped", "failed"}
        return {"alive": alive, "phase": phase.value}

    def readiness(self) -> Mapping[str, Any]:
        phase = self.lifecycle.phase()
        ready = phase.value == "ready"
        pd = self._pd_readiness()
        if pd.get("required") and not pd.get("ready"):
            ready = False
        return {"ready": ready, "phase": phase.value, "pd": pd}

    def health(self) -> Mapping[str, Any]:
        try:
            statuses = _run_coro(self.backends.health_all())
        except Exception as exc:
            return {
                "state": HealthState.UNHEALTHY.value,
                "error": str(exc),
                "lifecycle": self.lifecycle.snapshot(),
                "pd": self._pd_readiness(),
            }
        overall = self.backends.overall_health(statuses)
        payload: dict[str, Any] = {
            "state": overall.value,
            "lifecycle": self.lifecycle.snapshot(),
            "backends": {
                name: {
                    "state": st.state.value,
                    "latency_ms": st.latency_ms,
                    "message": st.message,
                    "details": dict(st.details),
                }
                for name, st in statuses.items()
            },
            "pd": self._pd_readiness(statuses),
        }
        if self.metrics is not None:
            payload["metrics"] = self.metrics.snapshot()
        return payload

    def _pd_readiness(self, statuses: Mapping[str, Any] | None = None) -> dict[str, Any]:
        cfg = self.config
        mode = str(getattr(cfg, "pd_mode", "off") or "off").lower()
        if mode not in {"soft", "native"}:
            return {"required": False, "ready": True, "mode": mode}
        prefill = str(getattr(cfg, "prefill_backend", "sglang") or "sglang")
        decode = str(getattr(cfg, "decode_backend", "llama_cpp") or "llama_cpp")
        status_map = statuses or {}
        if not status_map and self.backends_registry is not None:
            try:
                status_map = _run_coro(self.backends_registry.health_all())
            except Exception:
                status_map = {}

        def _ok(name: str) -> bool:
            # Decode may be served by tier aliases.
            candidates = [name]
            if name == "llama_cpp":
                candidates.extend(["tier2", "tier1", "tier3", "mock"])
            for cand in candidates:
                st = status_map.get(cand)
                if st is None:
                    continue
                state = getattr(st, "state", None)
                value = state.value if hasattr(state, "value") else str(state)
                if value == HealthState.HEALTHY.value:
                    return True
            return False

        prefill_ok = _ok(prefill)
        decode_ok = _ok(decode)
        return {
            "required": True,
            "ready": prefill_ok and decode_ok,
            "mode": mode,
            "prefill_backend": prefill,
            "decode_backend": decode,
            "prefill_healthy": prefill_ok,
            "decode_healthy": decode_ok,
        }


def _run_coro(coro):  # type: ignore[no-untyped-def]
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()
