"""Dependency-injection ports for peer subsystems.

Protocols only — Swarm Context never imports HAOE / DIPA / ARMORA / Mem0.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class IArmoraBudgetPort(Protocol):
    """Read frozen ARMORA BudgetEnvelope snapshot."""

    def envelope_id(self) -> str: ...

    def remaining(self) -> Mapping[str, float | None]: ...

    def is_frozen(self) -> bool: ...


@runtime_checkable
class IHaoeContextPort(Protocol):
    """Map Swarm Context ↔ HAOE CorrelationIds / baggage."""

    def to_correlation(self, context: Any) -> Mapping[str, str]: ...

    def apply_baggage(self, context: Any, baggage: Mapping[str, Any]) -> Any: ...


@runtime_checkable
class ITaskGraphContextPort(Protocol):
    """Supply condition maps / attach context to Task Graph execution."""

    def as_condition_map(self, context: Any) -> Mapping[str, Any]: ...

    def attach(self, context: Any, graph_id: str) -> Any: ...


@runtime_checkable
class IAgentRegistryPort(Protocol):
    """Resolve agent capability handles."""

    def resolve(self, agent_id: str) -> Mapping[str, Any] | None: ...

    def registry_revision(self) -> str: ...


@runtime_checkable
class IMetaOrchestratorPort(Protocol):
    """Future meta-orchestrator attach/detach of shared context."""

    def attach_context(self, context: Any) -> None: ...

    def detach_context(self, context_id: str) -> None: ...


@runtime_checkable
class IDipaContextPort(Protocol):
    """Inference-plane baggage keys for DIPA handlers."""

    def inference_baggage(self, context: Any) -> Mapping[str, Any]: ...


@runtime_checkable
class IGovernorPort(Protocol):
    """Consult pressure / budget before escalation."""

    def pressure_snapshot(self) -> Mapping[str, float]: ...

    def admit(self, context: Any) -> bool: ...


@runtime_checkable
class IMemoryRuntimePort(Protocol):
    """Resolve session / memory references (no Mem0 ownership)."""

    def resolve_session(self, session_id: str) -> Mapping[str, Any] | None: ...

    def resolve_ref(self, ref_id: str) -> Mapping[str, Any] | None: ...


@runtime_checkable
class IExperienceStorePort(Protocol):
    """Persist / load context snapshot blob handles."""

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...


@runtime_checkable
class ICheckpointManagerPort(Protocol):
    """Create / restore checkpoint metadata (persistence elsewhere)."""

    def create(self, metadata: Any) -> str: ...

    def restore(self, checkpoint_id: str) -> Any: ...


@runtime_checkable
class IDashboardPort(Protocol):
    """Export metrics shape for dashboards / RMF."""

    def export_metrics(self, context: Any) -> Mapping[str, float]: ...


@runtime_checkable
class IEventSink(Protocol):
    def emit(self, event: Any) -> None: ...


@runtime_checkable
class IMetricsSink(Protocol):
    def record(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None: ...
