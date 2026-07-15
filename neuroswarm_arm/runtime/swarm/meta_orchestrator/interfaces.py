"""Dependency-injection ports for peer subsystems.

Protocols only — Meta Orchestrator never imports HAOE / DIPA / ARMORA concretes.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .models import (
    AgentAssignment,
    ExecutionRequest,
    ExecutionSignal,
    NodeResult,
)


# Forward-friendly selection shape used by IAgentCatalogPort without importing registry.
@runtime_checkable
class ISelectionResultLike(Protocol):
    @property
    def agents(self) -> Sequence[Any]: ...


@runtime_checkable
class ITaskGraphPort(Protocol):
    """Access frozen Task Graph definition / readiness hints."""

    def get_graph(self, graph_id: str | None = None) -> Any: ...

    def node_ids(self) -> Sequence[str]: ...

    def predecessors(self, node_id: str) -> Sequence[str]: ...

    def successors(self, node_id: str) -> Sequence[str]: ...


@runtime_checkable
class IAgentCatalogPort(Protocol):
    """Candidate agent selection — not scheduling."""

    def select_for_task(self, request: Mapping[str, Any]) -> Any: ...

    def resolve_agent(self, agent_id: str) -> Mapping[str, Any] | None: ...


@runtime_checkable
class ISwarmContextPort(Protocol):
    """Attach / evolve / merge shared swarm context."""

    def get_context(self, context_id: str | None = None) -> Any: ...

    def attach(self, context: Any, *, execution_id: str) -> Any: ...

    def evolve(self, context: Any, **fields: Any) -> Any: ...

    def merge(self, parent: Any, child: Any) -> Any: ...


@runtime_checkable
class IHaoeExecutionPort(Protocol):
    """Submit execution requests to HAOE — HAOE owns scheduling."""

    async def submit(self, request: ExecutionRequest) -> str: ...

    async def poll(self, request_id: str) -> ExecutionSignal | None: ...

    async def cancel(self, request_id: str, *, forced: bool = False) -> None: ...


@runtime_checkable
class IArmoraBudgetPort(Protocol):
    """Read frozen ARMORA BudgetEnvelope snapshot."""

    def envelope_id(self) -> str: ...

    def remaining(self) -> Mapping[str, float | None]: ...

    def is_frozen(self) -> bool: ...


@runtime_checkable
class IDipaHintsPort(Protocol):
    """Inference-plane baggage keys for DIPA handlers (no inference)."""

    def inference_baggage(self, context: Any) -> Mapping[str, Any]: ...


@runtime_checkable
class ICheckpointManagerPort(Protocol):
    """Create / restore checkpoint metadata (persistence elsewhere)."""

    def create(self, metadata: Any) -> str: ...

    def restore(self, checkpoint_id: str) -> Any: ...


@runtime_checkable
class IExperienceStorePort(Protocol):
    """Persist / load workflow snapshot blob handles."""

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...


@runtime_checkable
class IDashboardPort(Protocol):
    """Export progress / metrics shape for dashboards / RMF."""

    def export_metrics(self, execution: Any) -> Mapping[str, float]: ...

    def export_progress(self, execution: Any) -> Mapping[str, Any]: ...


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


@runtime_checkable
class IMetaOrchestratorPort(Protocol):
    """Context attach/detach — matches swarm.context.IMetaOrchestratorPort."""

    def attach_context(self, context: Any) -> None: ...

    def detach_context(self, context_id: str) -> None: ...


# Re-export model symbols used by ports for typing convenience
__all__ = [
    "ITaskGraphPort",
    "IAgentCatalogPort",
    "ISwarmContextPort",
    "IHaoeExecutionPort",
    "IArmoraBudgetPort",
    "IDipaHintsPort",
    "ICheckpointManagerPort",
    "IExperienceStorePort",
    "IDashboardPort",
    "IEventSink",
    "IMetricsSink",
    "IMetaOrchestratorPort",
    "ISelectionResultLike",
    "AgentAssignment",
    "ExecutionRequest",
    "ExecutionSignal",
    "NodeResult",
]
