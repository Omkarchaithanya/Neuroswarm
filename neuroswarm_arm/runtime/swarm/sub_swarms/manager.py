"""SubSwarmManager — composition root / consumer facade."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .builder import SwarmBuilder
from .composer import SwarmComposer
from .events import EventBus, SwarmValidated
from .lifecycle import LifecycleState, is_selectable
from .metrics import SwarmMetrics
from .models import (
    ExecutableWorkflowDescription,
    ScoringWeights,
    SwarmSelectionRequest,
    SwarmSelectionResult,
    ValidationReport,
)
from .registry import SubSwarmRegistry
from .selector import SwarmSelector
from .serializer import SwarmSerializer
from .template import SwarmTemplate
from .validator import SwarmValidator


class SubSwarmManager:
    """Facade implementing consumer Protocols via structural typing.

    Templates only — never schedules, plans, or runs inference.
    """

    def __init__(
        self,
        registry: SubSwarmRegistry | None = None,
        *,
        events: EventBus | None = None,
        metrics: SwarmMetrics | None = None,
        weights: ScoringWeights | None = None,
        validator: SwarmValidator | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or SwarmMetrics()
        self.validator = validator or SwarmValidator()
        self.registry = registry or SubSwarmRegistry(
            events=self.events,
            metrics=self.metrics,
            validator=self.validator,
        )
        if registry is not None:
            self.registry.events = self.events
            self.registry.metrics = self.metrics
            self.registry.validator = self.validator

        self.selector = SwarmSelector(
            weights=weights,
            events=self.events,
            metrics=self.metrics,
        )
        self.composer = SwarmComposer()
        self.serializer = SwarmSerializer()

    # ---- registration ----
    def register(self, template: SwarmTemplate, **kwargs: Any) -> SwarmTemplate:
        return self.registry.register(template, **kwargs)

    def unregister(self, template_id: str) -> SwarmTemplate:
        return self.registry.unregister(template_id)

    def update(self, template_id: str, **fields: Any) -> SwarmTemplate:
        return self.registry.update(template_id, **fields)

    def get(self, template_id: str) -> SwarmTemplate:
        return self.registry.get(template_id)

    def list_templates(self) -> list[SwarmTemplate]:
        return self.registry.as_list()

    def list_ready(self) -> list[SwarmTemplate]:
        return self.registry.list_ready()

    def set_status(self, template_id: str, status: LifecycleState) -> SwarmTemplate:
        return self.registry.set_status(template_id, status)

    # ---- validation / selection / composition ----
    def validate(
        self,
        template: SwarmTemplate | str,
        *,
        known_agent_ids: Sequence[str] | None = None,
        strict: bool = False,
    ) -> ValidationReport:
        if isinstance(template, str):
            template = self.registry.get(template)
        report = self.validator.validate(
            template,
            registry=self.registry,
            known_agent_ids=known_agent_ids,
            strict=strict,
        )
        self.events.emit(
            SwarmValidated(
                template.id,
                ok=report.ok,
                error_count=len(report.errors),
                warning_count=len(report.warnings),
            )
        )
        return report

    def select(self, request: SwarmSelectionRequest) -> SwarmSelectionResult:
        return self.selector.select(self.registry.as_list(), request)

    def select_best(self, request: SwarmSelectionRequest, *, require: bool = False):
        return self.selector.select_best(
            self.registry.as_list(), request, require=require
        )

    def compose_merge(
        self,
        primary_id: str,
        secondary_id: str,
        *,
        register: bool = False,
        **kwargs: Any,
    ) -> SwarmTemplate:
        merged = self.composer.merge(
            self.registry.get(primary_id),
            self.registry.get(secondary_id),
            **kwargs,
        )
        if register:
            return self.register(merged)
        return merged

    def to_executable(
        self,
        template_id: str,
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> ExecutableWorkflowDescription:
        tpl = self.registry.get(template_id)
        desc = self.composer.to_executable(tpl, parameters=parameters)
        self.metrics.record_usage(template_id)
        return desc

    def builder(self) -> SwarmBuilder:
        return SwarmBuilder()

    # ---- serialization ----
    def dumps(self, template_id: str, *, fmt: str = "json") -> bytes:
        return self.serializer.dumps_template(
            self.registry.get(template_id), fmt=fmt  # type: ignore[arg-type]
        )

    def loads(self, data: bytes, *, fmt: str = "json", register: bool = False) -> SwarmTemplate:
        tpl = self.serializer.loads_template(data, fmt=fmt)  # type: ignore[arg-type]
        if register:
            return self.register(tpl)
        return tpl

    # ---- Protocol: IArmoraBudgetHintsPort ----
    def budget_hints(self, template_id: str) -> Mapping[str, Any]:
        tpl = self.registry.get(template_id)
        return {
            "estimated_cost": tpl.estimated_cost,
            "estimated_tokens": tpl.estimated_tokens,
            "max_cost_usd": tpl.profile.budget.max_cost_usd,
            "required_budget": list(tpl.required_budget),
        }

    def estimated_cost(self, template_id: str) -> float:
        return float(self.registry.get(template_id).estimated_cost)

    # ---- Protocol: IHaoeWorkflowHintsPort ----
    def workflow_type(self, template_id: str) -> str:
        return self.registry.get(template_id).workflow_type

    def parallelism_hint(self, template_id: str) -> int:
        return int(self.registry.get(template_id).parallelism)

    # ---- Protocol: IDipaModelHintsPort ----
    def preferred_models(self, template_id: str) -> list[str]:
        tpl = self.registry.get(template_id)
        return list(tpl.profile.model.preferred_models or tpl.required_models)

    def preferred_backends(self, template_id: str) -> list[str]:
        tpl = self.registry.get(template_id)
        pref = tpl.profile.backend.preferred_backend
        if pref:
            return [pref, *tpl.required_backends]
        return list(tpl.required_backends)

    # ---- Protocol: IDashboardSwarmView ----
    def template_metrics(self, template_id: str) -> Mapping[str, Any]:
        return {
            "usage": self.metrics.usage_count(template_id),
            "selection_frequency": self.metrics.selection_frequency(template_id),
            "success_rate": self.metrics.success_rate(template_id),
            "avg_latency_ms": self.metrics.average("nexus_sub_swarm_latency_ms"),
            "avg_cost_usd": self.metrics.average("nexus_sub_swarm_cost_usd"),
        }

    # ---- Protocol: ICheckpointTemplatePort ----
    def checkpoint_enabled(self, template_id: str) -> bool:
        return bool(self.registry.get(template_id).execution_profile.checkpoint_enabled)

    def create_template_checkpoint(
        self, template_id: str, metadata: Mapping[str, Any]
    ) -> str:
        # Metadata-only handle; persistence owned by Checkpoint Manager later.
        from ._utils import new_id

        _ = self.registry.get(template_id)
        return new_id("ckpt_")

    # ---- Protocol: ISwarmContextDefaultsPort ----
    def context_defaults(self, template_id: str) -> Mapping[str, Any]:
        return dict(self.registry.get(template_id).profile.context.defaults)

    def required_context_keys(self, template_id: str) -> Sequence[str]:
        return list(self.registry.get(template_id).required_context)

    # ---- Protocol: IMetaOrchestratorTemplatePort ----
    def accept_workflow_description(
        self, description: ExecutableWorkflowDescription
    ) -> str:
        """Ack description for coordination layer; does not execute."""
        self.metrics.record_usage(description.template_id)
        return description.template_id

    # ---- Protocol: IExperienceStoreTemplatePort ----
    def store_template_snapshot(self, snapshot: Mapping[str, Any]) -> str:
        from ._utils import new_id, stable_hash

        handle = new_id("snap_")
        # Local ack only — Experience Store owns persistence.
        _ = stable_hash(dict(snapshot))
        return handle

    def load_template_snapshot(self, handle: str) -> Mapping[str, Any] | None:
        _ = handle
        return None


def build_sub_swarm_manager(
    *,
    register_builtins: bool = True,
    promote_builtins_to_ready: bool = True,
    events: EventBus | None = None,
    metrics: SwarmMetrics | None = None,
    weights: ScoringWeights | None = None,
) -> SubSwarmManager:
    """Composition root for Sub Swarm subsystem."""
    manager = SubSwarmManager(events=events, metrics=metrics, weights=weights)
    if register_builtins:
        from .builtins import register_builtin_templates

        register_builtin_templates(
            manager.registry,
            promote_to_ready=promote_builtins_to_ready,
        )
    return manager
