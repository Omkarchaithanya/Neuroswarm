"""Dependency-injection ports for peer subsystems.

Protocols only — Rollback Manager never imports HAOE / DIPA / ARMORA concretes.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class IRollbackManagerPort(Protocol):
    """Plan / validate / execute rollback — Meta Orchestrator injection surface."""

    def plan(self, observation: Any, **kwargs: Any) -> Any: ...

    def validate(self, target: Any) -> Any: ...

    def execute(self, plan: Any) -> Any: ...


@runtime_checkable
class ICheckpointRollbackPort(Protocol):
    """Resolve checkpoint by id (read-only)."""

    def get_checkpoint(self, checkpoint_id: str) -> Any: ...

    def checkpoint_exists(self, checkpoint_id: str) -> bool: ...


@runtime_checkable
class IRecoveryPlannerPort(Protocol):
    """Accept recovery plan references from Checkpoint RecoveryPlanner."""

    def get_recovery_plan(self, plan_id: str) -> Any: ...

    def recovery_plan_exists(self, plan_id: str) -> bool: ...


@runtime_checkable
class ITaskGraphRollbackPort(Protocol):
    """Task Graph refs for consistency checks (no execution)."""

    def get_graph(self, graph_id: str | None = None) -> Any: ...

    def node_ids(self) -> Sequence[str]: ...

    def predecessors(self, node_id: str) -> Sequence[str]: ...

    def successors(self, node_id: str) -> Sequence[str]: ...


@runtime_checkable
class ISwarmContextRollbackPort(Protocol):
    """Swarm Context snapshot refs for context rollback."""

    def get_context(self, context_id: str | None = None) -> Any: ...

    def latest_snapshot_id(self, context_id: str) -> str | None: ...


@runtime_checkable
class IArmoraBudgetRollbackPort(Protocol):
    """Read frozen ARMORA budget envelope for budget rollback descriptors."""

    def envelope_id(self) -> str: ...

    def remaining(self) -> Mapping[str, float | None]: ...

    def is_frozen(self) -> bool: ...


@runtime_checkable
class IWorkflowCoordinationRollbackPort(Protocol):
    """Workflow Coordination Engine observation surface."""

    def get_execution(self, execution_id: str) -> Mapping[str, Any]: ...

    def completed_nodes(self, execution_id: str) -> Sequence[str]: ...

    def failed_nodes(self, execution_id: str) -> Sequence[str]: ...


@runtime_checkable
class IAgentRegistryRollbackPort(Protocol):
    """Agent Registry filter for rollback-capable agents."""

    def agents_with_rollback_support(self) -> Sequence[str]: ...


@runtime_checkable
class IExperienceStoreRollbackPort(Protocol):
    """Experience Store refs for dangling-reference checks."""

    def experience_exists(self, experience_id: str) -> bool: ...

    def attach_rollback_refs(
        self,
        execution_id: str,
        rollback_ids: list[str],
    ) -> None: ...


@runtime_checkable
class IHaoeRollbackPort(Protocol):
    """HAOE observation hooks (no scheduling)."""

    def observe_execution(self, execution_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class IDashboardRollbackPort(Protocol):
    """Export rollback metrics / status for dashboards."""

    def export_rollback_metrics(self, workflow_id: str) -> Mapping[str, float]: ...


@runtime_checkable
class IPerformixRollbackPort(Protocol):
    """Performix hooks for rollback latency samples."""

    def record_rollback_sample(
        self,
        rollback_id: str,
        *,
        duration_ms: float,
        strategy: str,
    ) -> None: ...


@runtime_checkable
class IPolicyPredicatePort(Protocol):
    """External policy engine predicates for custom rollback policies."""

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
    "IRollbackManagerPort",
    "ICheckpointRollbackPort",
    "IRecoveryPlannerPort",
    "ITaskGraphRollbackPort",
    "ISwarmContextRollbackPort",
    "IArmoraBudgetRollbackPort",
    "IWorkflowCoordinationRollbackPort",
    "IAgentRegistryRollbackPort",
    "IExperienceStoreRollbackPort",
    "IHaoeRollbackPort",
    "IDashboardRollbackPort",
    "IPerformixRollbackPort",
    "IPolicyPredicatePort",
    "IEventSink",
    "IMetricsSink",
]
