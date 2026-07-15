"""AQR backend registry facade — probes DIPA BackendRegistry + known runtimes."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..catalog.quant_catalog import QuantCatalog
from ..models import BackendStatus


class SupportsBackendHealth(Protocol):
    def health_all(self) -> Mapping[str, Any]: ...
    def names(self) -> list[str]: ...
    def get(self, name: str) -> Any: ...


_DEFAULT_CAPS: dict[str, dict[str, Any]] = {
    "llama_cpp": {
        "streaming": True,
        "batching": False,
        "speculative_decode": True,
        "kv_sharing": True,
        "numa_aware": True,
        "quants": ["Q2_K", "Q3_K", "Q4_0", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "BF16", "FP16"],
    },
    "vllm": {
        "streaming": True,
        "batching": True,
        "speculative_decode": True,
        "kv_sharing": True,
        "numa_aware": False,
        "quants": ["Q4_0", "Q4_K_M", "Q5_K_M", "Q8_0", "INT8", "BF16", "FP16"],
    },
    "executorch": {
        "streaming": False,
        "batching": False,
        "speculative_decode": False,
        "kv_sharing": False,
        "numa_aware": False,
        "quants": ["Q4_0", "INT8"],
    },
    "litert": {
        "streaming": False,
        "batching": False,
        "speculative_decode": False,
        "kv_sharing": False,
        "numa_aware": False,
        "quants": ["Q4_0", "INT8"],
    },
    "sglang": {
        "streaming": True,
        "batching": True,
        "speculative_decode": True,
        "kv_sharing": True,
        "numa_aware": False,
        "quants": ["Q4_K_M", "Q5_K_M", "FP16", "BF16"],
    },
    "mock": {
        "streaming": True,
        "batching": True,
        "speculative_decode": False,
        "kv_sharing": False,
        "numa_aware": False,
        "quants": ["Q4_0", "Q4_K_M", "Q5_K_M", "Q8_0"],
    },
}


class AQRBackendRegistry:
    def __init__(
        self,
        dipa_backends: Any | None = None,
        *,
        quant_catalog: QuantCatalog | None = None,
        probe_names: list[str] | None = None,
    ) -> None:
        self._dipa = dipa_backends
        self._quants = quant_catalog
        self._probe = list(probe_names or list(_DEFAULT_CAPS.keys()))
        self._cache: list[BackendStatus] = []

    def refresh(self) -> list[BackendStatus]:
        statuses: list[BackendStatus] = []
        health: dict[str, Any] = {}
        registered: set[str] = set()
        if self._dipa is not None:
            try:
                health = dict(self._dipa.health_all() or {})
            except Exception:
                health = {}
            try:
                registered = set(self._dipa.names())
            except Exception:
                registered = set(health.keys())

        # Tier backends (tier1/2/3) map to llama_cpp
        for name, info in health.items():
            state = str(info.get("state", info) if isinstance(info, dict) else info)
            healthy = state.lower() == "healthy"
            kind = "llama_cpp" if name.startswith("tier") else name
            caps = _DEFAULT_CAPS.get(kind, _DEFAULT_CAPS["llama_cpp"])
            statuses.append(
                BackendStatus(
                    name=name,
                    available=True,
                    healthy=healthy,
                    supported_quants=list(caps.get("quants", [])),
                    supported_models=[name] if name.startswith("tier") else [],
                    latency_ms=float(info.get("latency_ms", 0.0)) if isinstance(info, dict) else 0.0,
                    streaming=bool(caps.get("streaming", True)),
                    batching=bool(caps.get("batching", False)),
                    speculative_decode=bool(caps.get("speculative_decode", False)),
                    kv_sharing=bool(caps.get("kv_sharing", False)),
                    numa_aware=bool(caps.get("numa_aware", False)),
                    details={"kind": kind, "state": state},
                )
            )

        for kind in self._probe:
            if any(s.details.get("kind") == kind or s.name == kind for s in statuses):
                continue
            caps = _DEFAULT_CAPS.get(kind, {})
            present = kind in registered or any(
                s.name == kind for s in statuses
            )
            # Future runtimes: available only if registered; else detect-as-absent
            statuses.append(
                BackendStatus(
                    name=kind,
                    available=present,
                    healthy=present,
                    supported_quants=list(caps.get("quants", [])),
                    streaming=bool(caps.get("streaming", False)),
                    batching=bool(caps.get("batching", False)),
                    speculative_decode=bool(caps.get("speculative_decode", False)),
                    kv_sharing=bool(caps.get("kv_sharing", False)),
                    numa_aware=bool(caps.get("numa_aware", False)),
                    details={"kind": kind, "probed": True, "registered": present},
                )
            )

        # Always ensure logical llama_cpp aggregate if tiers exist
        if any(s.name.startswith("tier") for s in statuses) and not any(
            s.name == "llama_cpp" for s in statuses
        ):
            tier_ok = any(s.healthy for s in statuses if s.name.startswith("tier"))
            caps = _DEFAULT_CAPS["llama_cpp"]
            statuses.append(
                BackendStatus(
                    name="llama_cpp",
                    available=True,
                    healthy=tier_ok or True,  # planning-time healthy if tiers configured
                    supported_quants=list(caps["quants"]),
                    supported_models=["tier1", "tier2", "tier3"],
                    streaming=True,
                    speculative_decode=True,
                    kv_sharing=True,
                    numa_aware=True,
                    details={"kind": "llama_cpp", "aggregate": True},
                )
            )

        self._cache = statuses
        return statuses

    def list(self) -> list[BackendStatus]:
        if not self._cache:
            return self.refresh()
        return list(self._cache)

    def healthy(self) -> list[BackendStatus]:
        return [b for b in self.list() if b.available and b.healthy]
