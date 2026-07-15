"""Dependency-injection ports for peer subsystems.

Protocols only — Checkpoint Manager never imports HAOE / DIPA / ARMORA concretes.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class ICheckpointManagerPort(Protocol):
    """Create / restore checkpoint metadata — matches Meta Orchestrator / Context."""

    def create(self, metadata: Any) -> str: ...

    def restore(self, checkpoint_id: str) -> Any: ...


@runtime_checkable
class IExperienceStorePort(Protocol):
    """Persist / load workflow snapshot blob handles."""

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...


@runtime_checkable
class ICheckpointExperiencePort(Protocol):
    """Checkpoint Manager → Experience Store: checkpoint refs only."""

    def attach_checkpoint_refs(
        self,
        execution_id: str,
        checkpoint_ids: list[str],
    ) -> None: ...


@runtime_checkable
class IArmoraCheckpointPort(Protocol):
    """Read frozen ARMORA budget envelope for budget snapshots."""

    def envelope_id(self) -> str: ...

    def remaining(self) -> Mapping[str, float | None]: ...

    def is_frozen(self) -> bool: ...


@runtime_checkable
class IHaoeCheckpointPort(Protocol):
    """HAOE observation hooks for checkpoint policies (no scheduling)."""

    def observe_execution(self, execution_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ITaskGraphCheckpointPort(Protocol):
    """Task Graph refs for graph snapshots (no execution)."""

    def get_graph(self, graph_id: str | None = None) -> Any: ...

    def node_ids(self) -> Sequence[str]: ...

    def predecessors(self, node_id: str) -> Sequence[str]: ...

    def successors(self, node_id: str) -> Sequence[str]: ...


@runtime_checkable
class IAgentRegistryCheckpointPort(Protocol):
    """Agent Registry filter for checkpoint-capable agents."""

    def agents_with_checkpoint_support(self) -> Sequence[str]: ...


@runtime_checkable
class ISwarmContextCheckpointPort(Protocol):
    """Swarm Context snapshot refs for context checkpoints."""

    def get_context(self, context_id: str | None = None) -> Any: ...

    def latest_snapshot_id(self, context_id: str) -> str | None: ...


@runtime_checkable
class IWorkflowCoordinationCheckpointPort(Protocol):
    """Workflow Coordination Engine observation surface."""

    def get_execution(self, execution_id: str) -> Mapping[str, Any]: ...

    def completed_nodes(self, execution_id: str) -> Sequence[str]: ...


@runtime_checkable
class IDashboardCheckpointPort(Protocol):
    """Export checkpoint metrics / recovery status for dashboards."""

    def export_checkpoint_metrics(self, workflow_id: str) -> Mapping[str, float]: ...


@runtime_checkable
class IPerformixCheckpointPort(Protocol):
    """Performix hooks for checkpoint size / latency samples."""

    def record_checkpoint_sample(
        self,
        checkpoint_id: str,
        *,
        size_bytes: int,
        latency_ms: float,
    ) -> None: ...


@runtime_checkable
class IPolicyEngineCheckpointPort(Protocol):
    """External policy engine predicates for custom checkpoint policies."""

    def evaluate_predicate(
        self,
        predicate_id: str,
        observation: Mapping[str, Any],
    ) -> bool: ...


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


__all__ = [
    "ICheckpointManagerPort",
    "IExperienceStorePort",
    "ICheckpointExperiencePort",
    "IArmoraCheckpointPort",
    "IHaoeCheckpointPort",
    "ITaskGraphCheckpointPort",
    "IAgentRegistryCheckpointPort",
    "ISwarmContextCheckpointPort",
    "IWorkflowCoordinationCheckpointPort",
    "IDashboardCheckpointPort",
    "IPerformixCheckpointPort",
    "IPolicyEngineCheckpointPort",
    "IEventSink",
    "IMetricsSink",
]
