"""Consumer-facing Protocol interfaces (no kernel imports)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .models import ExecutableWorkflowDescription, SwarmSelectionRequest, SwarmSelectionResult
from .template import SwarmTemplate


@runtime_checkable
class ITaskGraphTemplatePort(Protocol):
    """Task Graph: resolve / attach graph references for templates."""

    def resolve_graph(self, graph_id: str) -> Mapping[str, Any] | None: ...

    def attach_graph_snapshot(self, template_id: str, snapshot: Mapping[str, Any]) -> None: ...


@runtime_checkable
class IAgentRegistryLookupPort(Protocol):
    """Agent Registry: resolve agent ids / types referenced by templates."""

    def resolve_agent_id(self, agent_id: str) -> Any | None: ...

    def resolve_agent_type(self, agent_type: str) -> Any | None: ...

    def list_agent_ids(self) -> Sequence[str]: ...


@runtime_checkable
class ISwarmContextDefaultsPort(Protocol):
    """Swarm Context: default context keys for a template."""

    def context_defaults(self, template_id: str) -> Mapping[str, Any]: ...

    def required_context_keys(self, template_id: str) -> Sequence[str]: ...


@runtime_checkable
class IMetaOrchestratorTemplatePort(Protocol):
    """Meta Orchestrator: accept executable workflow descriptions (no run here)."""

    def accept_workflow_description(
        self, description: ExecutableWorkflowDescription
    ) -> str: ...


@runtime_checkable
class IArmoraBudgetHintsPort(Protocol):
    """ARMORA: budget hints from template estimates."""

    def budget_hints(self, template_id: str) -> Mapping[str, Any]: ...

    def estimated_cost(self, template_id: str) -> float: ...


@runtime_checkable
class IHaoeWorkflowHintsPort(Protocol):
    """HAOE: workflow-type / parallelism hints from templates."""

    def workflow_type(self, template_id: str) -> str: ...

    def parallelism_hint(self, template_id: str) -> int: ...


@runtime_checkable
class IDipaModelHintsPort(Protocol):
    """DIPA: preferred models / backends from templates."""

    def preferred_models(self, template_id: str) -> list[str]: ...

    def preferred_backends(self, template_id: str) -> list[str]: ...


@runtime_checkable
class IExperienceStoreTemplatePort(Protocol):
    """Experience Store: record template selection / usage snapshots."""

    def store_template_snapshot(self, snapshot: Mapping[str, Any]) -> str: ...

    def load_template_snapshot(self, handle: str) -> Mapping[str, Any] | None: ...


@runtime_checkable
class ICheckpointTemplatePort(Protocol):
    """Checkpoint Manager: template-level checkpoint metadata hooks."""

    def checkpoint_enabled(self, template_id: str) -> bool: ...

    def create_template_checkpoint(self, template_id: str, metadata: Mapping[str, Any]) -> str: ...


@runtime_checkable
class IDashboardSwarmView(Protocol):
    """Dashboard: list templates + metrics."""

    def list_templates(self) -> list[SwarmTemplate]: ...

    def template_metrics(self, template_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ISubSwarmCatalog(Protocol):
    """Generic catalog for consumers that only need get/list/select."""

    def get(self, template_id: str) -> SwarmTemplate: ...

    def list_ready(self) -> list[SwarmTemplate]: ...

    def select(self, request: SwarmSelectionRequest) -> SwarmSelectionResult: ...
