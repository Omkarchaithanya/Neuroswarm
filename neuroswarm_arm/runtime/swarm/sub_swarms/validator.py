"""Swarm template validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .exceptions import ValidationError
from .lifecycle import LifecycleState
from .models import ValidationReport
from .versioning import parse_semver

if TYPE_CHECKING:
    from .registry import SubSwarmRegistry
    from .template import SwarmTemplate


class SwarmValidator:
    """Validate swarm templates and registry invariants."""

    def validate(
        self,
        template: SwarmTemplate,
        *,
        registry: SubSwarmRegistry | None = None,
        known_agent_ids: Iterable[str] | None = None,
        strict: bool = False,
    ) -> ValidationReport:
        report = ValidationReport()

        if not template.task_graph_reference.is_present:
            report.add(
                "missing_task_graph",
                "task_graph_reference is empty",
                field="task_graph_reference",
            )
        elif template.task_graph_reference.snapshot is None:
            report.add(
                "missing_task_graph_snapshot",
                "task_graph_reference.snapshot is None",
                field="task_graph_reference.snapshot",
                severity="warning",
            )

        if not template.required_agents:
            report.add(
                "missing_agents",
                "required_agents is empty",
                field="required_agents",
            )

        try:
            parse_semver(template.version)
        except Exception as exc:  # noqa: BLE001
            report.add(
                "invalid_version",
                str(exc),
                field="version",
            )

        known = set(known_agent_ids or [])
        if known:
            for agent_id in template.required_agents:
                if agent_id not in known:
                    report.add(
                        "unknown_agent",
                        f"required agent not in registry: {agent_id}",
                        field="required_agents",
                    )

        # Capability constraints
        for cap in template.constraints.required_capabilities:
            if cap not in template.capabilities.capability_keys():
                report.add(
                    "invalid_capability",
                    f"constraint capability not declared: {cap}",
                    field="constraints.required_capabilities",
                )

        for tool in template.constraints.required_tools:
            if tool not in template.required_tools:
                report.add(
                    "missing_tool",
                    f"constraint tool not listed: {tool}",
                    field="required_tools",
                    severity="warning",
                )

        for model in template.constraints.required_models:
            if model not in template.required_models:
                report.add(
                    "missing_model",
                    f"constraint model not listed: {model}",
                    field="required_models",
                    severity="warning",
                )

        if template.required_context or template.constraints.required_context:
            needed = set(template.required_context) | set(
                template.constraints.required_context
            )
            profile_keys = set(template.profile.context.required_keys)
            missing_ctx = needed - profile_keys - set(template.required_context)
            # required_context on template itself counts as declared
            if not template.required_context and needed:
                report.add(
                    "missing_context",
                    f"required context keys undeclared: {sorted(needed)}",
                    field="required_context",
                )

        if template.required_budget or template.constraints.required_budget_keys:
            needed_b = set(template.required_budget) | set(
                template.constraints.required_budget_keys
            )
            if needed_b and not template.required_budget:
                report.add(
                    "missing_budget",
                    f"required budget keys undeclared: {sorted(needed_b)}",
                    field="required_budget",
                )

        if not template.constraints.agent_count_ok(template.agent_count()):
            report.add(
                "agent_count",
                f"agent count {template.agent_count()} outside constraints "
                f"(min={template.constraints.min_agents}, "
                f"max={template.constraints.max_agents})",
                field="required_agents",
            )

        if not template.constraints.within_budget(
            cost=template.estimated_cost,
            latency_ms=template.estimated_latency,
            memory_bytes=template.estimated_memory,
            cpu_cores=template.estimated_cpu,
            tokens=template.estimated_tokens,
        ):
            report.add(
                "budget_limits",
                "estimated resources exceed constraint limits",
                field="constraints",
            )

        # Circular composition via provenance
        chain = list(template.metadata.composition_of) + list(
            template.metadata.provenance
        )
        if template.id in chain:
            report.add(
                "circular_composition",
                f"template id appears in composition chain: {template.id}",
                field="metadata.composition_of",
            )

        if registry is not None:
            existing = registry.get_optional(template.id)
            if existing is not None and existing is not template:
                # duplicate check for prospective register
                pass
            by_name = [
                t
                for t in registry.as_list()
                if t.name == template.name and t.id != template.id
            ]
            if by_name:
                report.add(
                    "duplicate_name",
                    f"duplicate template name: {template.name}",
                    field="name",
                    severity="warning",
                )

        if template.status is LifecycleState.ARCHIVED:
            report.add(
                "archived",
                "template is archived",
                field="status",
                severity="warning",
            )

        if strict and not report.ok:
            msgs = "; ".join(i.message for i in report.errors)
            raise ValidationError(msgs)

        return report

    def validate_no_duplicate(
        self,
        template: SwarmTemplate,
        registry: SubSwarmRegistry,
    ) -> ValidationReport:
        report = ValidationReport()
        if registry.get_optional(template.id) is not None:
            report.add(
                "duplicate_template",
                f"template id already registered: {template.id}",
                field="id",
            )
        return report
