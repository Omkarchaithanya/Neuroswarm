"""Dependency-injection ports for peer subsystems.

Protocols only — RMRE never imports ARMORA / HAOE / DIPA / Swarm concretes.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class IArmoraResiliencePort(Protocol):
    """Read frozen ARMORA budget envelope for constraint / health evaluation."""

    def envelope_id(self) -> str: ...

    def remaining(self) -> Mapping[str, float | None]: ...

    def is_frozen(self) -> bool: ...


@runtime_checkable
class IDipaResiliencePort(Protocol):
    """Observe / apply plan patches — caller implements; RMRE never executes."""

    def active_plan(self, execution_id: str) -> Mapping[str, Any]: ...

    def apply_plan_patch(
        self,
        execution_id: str,
        patch: Mapping[str, Any],
    ) -> None: ...


@runtime_checkable
class IHaoeResiliencePort(Protocol):
    """HAOE observation hooks (no scheduling)."""

    def observe_execution(self, execution_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ITaskGraphResiliencePort(Protocol):
    """Task Graph workload / node hints."""

    def get_graph(self, graph_id: str | None = None) -> Any: ...

    def node_ids(self) -> Sequence[str]: ...

    def workload_hint(self, node_id: str) -> str: ...


@runtime_checkable
class ISwarmContextResiliencePort(Protocol):
    """Swarm Context length / tool flags."""

    def get_context(self, context_id: str | None = None) -> Any: ...

    def context_tokens(self, context_id: str) -> int: ...

    def tools_enabled(self, context_id: str) -> bool: ...


@runtime_checkable
class IExperienceStorePort(Protocol):
    """Persist recovery snapshot refs (Experience Store)."""

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...


@runtime_checkable
class ICheckpointManagerPort(Protocol):
    """Optional recovery-point reference."""

    def create(self, metadata: Any) -> str: ...

    def restore(self, checkpoint_id: str) -> Any: ...


@runtime_checkable
class IDashboardResiliencePort(Protocol):
    """Export resilience metrics for dashboards."""

    def export_resilience_metrics(self, execution_id: str) -> Mapping[str, float]: ...


@runtime_checkable
class IPerformixResiliencePort(Protocol):
    """Performix hooks for degradation / latency samples."""

    def record_resilience_sample(
        self,
        execution_id: str,
        *,
        quality_delta: float,
        latency_delta: float,
        cost_delta: float,
    ) -> None: ...


@runtime_checkable
class IBenchmarkRuntimePort(Protocol):
    """Export benchmark rows for Performix / offline analysis."""

    def export_benchmark_row(self, row: Mapping[str, Any]) -> None: ...


@runtime_checkable
class IPolicyEnginePort(Protocol):
    """External policy engine predicates for custom resilience policies."""

    def evaluate_predicate(
        self,
        name: str,
        context: Mapping[str, Any],
    ) -> bool: ...


@runtime_checkable
class IEventSink(Protocol):
    """Optional external event sink (OTel / ROF)."""

    def emit(self, event: Any) -> None: ...


@runtime_checkable
class IMetricsSink(Protocol):
    """Optional external metrics sink (RMF / Prometheus)."""

    def record(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None: ...
