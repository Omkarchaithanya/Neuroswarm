"""Consumer Protocol ports for Experience Store integration.

No peer-kernel implementations here — structural typing only.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .execution_record import ExecutionRecord
from .filters import ExperienceFilter
from .workflow_record import WorkflowRecord


@runtime_checkable
class IArmoraExperiencePort(Protocol):
    """ARMORA → Experience Store: budget / cost / energy accounting hooks."""

    def record_budget_outcome(
        self,
        execution_id: str,
        *,
        estimated_cost: float,
        estimated_energy: float,
        budget: Mapping[str, Any] | None = None,
    ) -> None: ...


@runtime_checkable
class IHaoeExperiencePort(Protocol):
    """HAOE → Experience Store: completed workflow recording."""

    def record_workflow_execution(self, record: ExecutionRecord) -> ExecutionRecord: ...


@runtime_checkable
class ITaskGraphExperiencePort(Protocol):
    """Task Graph → Experience Store: definition hash + metrics snapshot."""

    def record_graph_execution(
        self,
        *,
        task_graph_reference: str,
        execution: ExecutionRecord,
    ) -> ExecutionRecord: ...


@runtime_checkable
class IAgentRegistryExperiencePort(Protocol):
    """Agent Registry → Experience Store: assignment / selection outcomes."""

    def record_agent_assignments(
        self,
        execution_id: str,
        assignments: list[Mapping[str, Any]],
    ) -> None: ...


@runtime_checkable
class ISwarmContextExperiencePort(Protocol):
    """Swarm Context → Experience Store: snapshot handles."""

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...


@runtime_checkable
class IWorkflowCoordinationPort(Protocol):
    """Workflow Coordination Engine → Experience Store."""

    def record_workflow(self, record: WorkflowRecord) -> WorkflowRecord: ...


@runtime_checkable
class ICheckpointExperiencePort(Protocol):
    """Checkpoint Manager → Experience Store: checkpoint refs only."""

    def attach_checkpoint_refs(
        self,
        execution_id: str,
        checkpoint_ids: list[str],
    ) -> None: ...


@runtime_checkable
class IDashboardExperiencePort(Protocol):
    """Dashboard → Experience Store: read models."""

    def query(self, filt: ExperienceFilter | None = None) -> list[ExecutionRecord]: ...

    def export_metrics(self) -> Mapping[str, float]: ...


@runtime_checkable
class IPerformixExperiencePort(Protocol):
    """Performix / RPF → Experience Store: flamegraph / PMU artifact refs."""

    def attach_performix_artifact(
        self,
        execution_id: str,
        *,
        uri: str,
        label: str | None = None,
    ) -> None: ...


@runtime_checkable
class IBenchmarkRuntimePort(Protocol):
    """Benchmark Runtime → Experience Store: dataset generation."""

    def generate_benchmark_dataset(
        self,
        filt: ExperienceFilter | None = None,
    ) -> Any: ...


@runtime_checkable
class IPolicyEnginePort(Protocol):
    """Policy Engine / future GEPA → Experience Store: policy dataset read."""

    def generate_policy_dataset(
        self,
        filt: ExperienceFilter | None = None,
    ) -> Any: ...


@runtime_checkable
class IExperienceStorePort(Protocol):
    """Canonical snapshot port (compatible with swarm.context.interfaces)."""

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...
