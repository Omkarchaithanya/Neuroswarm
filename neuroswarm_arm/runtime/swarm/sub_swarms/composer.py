"""SwarmComposer — merge / extend / clone / override / parameterize templates."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .exceptions import CircularCompositionError, CompositionError
from .metadata import SwarmMetadata, merge_labels, merge_tags
from .models import ExecutableWorkflowDescription
from .profile import SwarmProfile
from .template import SwarmTemplate
from .versioning import bump_semver


class SwarmComposer:
    """Compose reusable workflow descriptions. No execution."""

    def clone(
        self,
        template: SwarmTemplate,
        *,
        new_id: str | None = None,
        new_name: str | None = None,
    ) -> SwarmTemplate:
        return template.clone(new_id=new_id, new_name=new_name)

    def extend(
        self,
        base: SwarmTemplate,
        *,
        extra_agents: Sequence[str] | None = None,
        extra_tools: Sequence[str] | None = None,
        extra_models: Sequence[str] | None = None,
        extra_backends: Sequence[str] | None = None,
        extra_context: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        labels: Mapping[str, str] | None = None,
        profile: SwarmProfile | None = None,
        metadata_extra: Mapping[str, Any] | None = None,
        new_id: str | None = None,
        new_name: str | None = None,
    ) -> SwarmTemplate:
        self._assert_no_cycle(base, [base.id])
        cloned = base.clone(
            new_id=new_id or f"{base.id}.extended",
            new_name=new_name or f"{base.name}_extended",
        )
        meta = cloned.metadata.model_copy(
            update={
                "composition_of": list(
                    dict.fromkeys([*cloned.metadata.composition_of, base.id])
                ),
                "provenance": list(
                    dict.fromkeys([*cloned.metadata.provenance, base.id])
                ),
                "extra": {
                    **cloned.metadata.extra,
                    **dict(metadata_extra or {}),
                },
            }
        )
        return cloned.evolve(
            required_agents=list(
                dict.fromkeys([*cloned.required_agents, *(extra_agents or [])])
            ),
            required_tools=list(
                dict.fromkeys([*cloned.required_tools, *(extra_tools or [])])
            ),
            required_models=list(
                dict.fromkeys([*cloned.required_models, *(extra_models or [])])
            ),
            required_backends=list(
                dict.fromkeys([*cloned.required_backends, *(extra_backends or [])])
            ),
            required_context=list(
                dict.fromkeys([*cloned.required_context, *(extra_context or [])])
            ),
            tags=merge_tags(cloned.tags, tags),
            labels=merge_labels(cloned.labels, labels),
            profile=cloned.profile.merge(profile) if profile else cloned.profile,
            metadata=meta,
            version=bump_semver(base.version, part="minor"),
        )

    def override(
        self,
        base: SwarmTemplate,
        **fields: Any,
    ) -> SwarmTemplate:
        self._assert_no_cycle(base, [base.id])
        forbidden = {"id", "created_at"}
        bad = forbidden & set(fields)
        if bad:
            raise CompositionError(f"cannot override fields: {sorted(bad)}")
        meta = base.metadata
        if "metadata" not in fields:
            meta = base.metadata.model_copy(
                update={
                    "composition_of": list(
                        dict.fromkeys([*base.metadata.composition_of, base.id])
                    ),
                }
            )
            fields = {**fields, "metadata": meta}
        return base.clone(
            new_id=fields.pop("new_id", f"{base.id}.override"),
            new_name=fields.pop("new_name", f"{base.name}_override"),
        ).evolve(**fields)

    def merge(
        self,
        primary: SwarmTemplate,
        secondary: SwarmTemplate,
        *,
        new_id: str | None = None,
        new_name: str | None = None,
    ) -> SwarmTemplate:
        """Merge two templates; primary wins on scalar conflicts."""
        chain = [primary.id, secondary.id]
        self._assert_no_cycle(primary, chain)
        self._assert_no_cycle(secondary, chain)
        if primary.id in secondary.metadata.composition_of or secondary.id in primary.metadata.composition_of:
            # still allow merge but detect self-reference loops
            pass
        if primary.id == secondary.id:
            raise CircularCompositionError([primary.id, secondary.id])

        meta = SwarmMetadata(
            owner=primary.metadata.owner or secondary.metadata.owner,
            team=primary.metadata.team or secondary.metadata.team,
            source=primary.metadata.source,
            provenance=list(
                dict.fromkeys(
                    [
                        *primary.metadata.provenance,
                        *secondary.metadata.provenance,
                        primary.id,
                        secondary.id,
                    ]
                )
            ),
            composition_of=list(
                dict.fromkeys(
                    [
                        *primary.metadata.composition_of,
                        *secondary.metadata.composition_of,
                        primary.id,
                        secondary.id,
                    ]
                )
            ),
            notes=primary.metadata.notes or secondary.metadata.notes,
            extra={**secondary.metadata.extra, **primary.metadata.extra},
        )
        self._detect_cycle_in_list(meta.composition_of)

        return SwarmTemplate(
            id=new_id or f"{primary.id}+{secondary.name}",
            name=new_name or f"{primary.name}_merged",
            display_name=primary.display_name or secondary.display_name,
            description=primary.description or secondary.description,
            version=bump_semver(primary.version, part="minor"),
            category=primary.category or secondary.category,
            workflow_type=primary.workflow_type or secondary.workflow_type,
            task_graph_reference=primary.task_graph_reference
            if primary.task_graph_reference.is_present
            else secondary.task_graph_reference,
            required_agents=list(
                dict.fromkeys(
                    [*primary.required_agents, *secondary.required_agents]
                )
            ),
            optional_agents=list(
                dict.fromkeys(
                    [*primary.optional_agents, *secondary.optional_agents]
                )
            ),
            required_tools=list(
                dict.fromkeys([*primary.required_tools, *secondary.required_tools])
            ),
            required_models=list(
                dict.fromkeys([*primary.required_models, *secondary.required_models])
            ),
            required_backends=list(
                dict.fromkeys(
                    [*primary.required_backends, *secondary.required_backends]
                )
            ),
            required_memory=list(
                dict.fromkeys([*primary.required_memory, *secondary.required_memory])
            ),
            required_context=list(
                dict.fromkeys(
                    [*primary.required_context, *secondary.required_context]
                )
            ),
            required_budget=list(
                dict.fromkeys([*primary.required_budget, *secondary.required_budget])
            ),
            execution_profile=primary.execution_profile,
            profile=primary.profile.merge(secondary.profile),
            capabilities=primary.capabilities,
            constraints=primary.constraints,
            estimated_cost=max(primary.estimated_cost, secondary.estimated_cost),
            estimated_latency=max(primary.estimated_latency, secondary.estimated_latency),
            estimated_memory=max(primary.estimated_memory, secondary.estimated_memory),
            estimated_cpu=max(primary.estimated_cpu, secondary.estimated_cpu),
            estimated_tokens=max(primary.estimated_tokens, secondary.estimated_tokens),
            parallelism=max(primary.parallelism, secondary.parallelism),
            priority=max(primary.priority, secondary.priority),
            timeout=primary.timeout if primary.timeout is not None else secondary.timeout,
            retry_policy=primary.retry_policy,
            metadata=meta,
            tags=merge_tags(primary.tags, secondary.tags),
            labels=merge_labels(primary.labels, secondary.labels),
        )

    def parameterize(
        self,
        template: SwarmTemplate,
        parameters: Mapping[str, Any],
        *,
        new_id: str | None = None,
        new_name: str | None = None,
    ) -> SwarmTemplate:
        """Apply parameter overrides into metadata.extra + selective fields."""
        params = dict(parameters)
        field_overrides: dict[str, Any] = {}
        for key in (
            "priority",
            "timeout",
            "parallelism",
            "estimated_cost",
            "estimated_latency",
            "workflow_type",
            "category",
        ):
            if key in params:
                field_overrides[key] = params.pop(key)

        meta = template.metadata.model_copy(
            update={
                "extra": {
                    **template.metadata.extra,
                    "parameters": params,
                },
                "composition_of": list(
                    dict.fromkeys([*template.metadata.composition_of, template.id])
                ),
            }
        )
        return template.clone(
            new_id=new_id or f"{template.id}.param",
            new_name=new_name or f"{template.name}_param",
        ).evolve(metadata=meta, **field_overrides)

    def to_executable(
        self,
        template: SwarmTemplate,
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> ExecutableWorkflowDescription:
        params = dict(parameters or {})
        return ExecutableWorkflowDescription(
            template_id=template.id,
            template_name=template.name,
            template_version=template.version,
            workflow_type=template.workflow_type,
            task_graph=template.task_graph_reference,
            agents=list(template.required_agents),
            optional_agents=list(template.optional_agents),
            required_tools=list(template.required_tools),
            required_models=list(template.required_models),
            required_backends=list(template.required_backends),
            context_defaults={
                **template.profile.context.defaults,
                **{k: params[k] for k in template.required_context if k in params},
            },
            budget_defaults={
                "max_cost_usd": template.profile.budget.max_cost_usd
                or template.estimated_cost,
                "max_tokens": template.profile.budget.max_tokens
                or template.estimated_tokens,
                "required_keys": list(template.required_budget),
            },
            constraints=template.constraints.model_dump(mode="json"),
            execution_profile=template.execution_profile.model_dump(mode="json"),
            parameters=params,
            metadata={
                "category": template.category,
                "tags": list(template.tags),
                "labels": dict(template.labels),
            },
        )

    def _assert_no_cycle(self, template: SwarmTemplate, visiting: list[str]) -> None:
        chain = list(template.metadata.composition_of)
        self._detect_cycle_in_list([*visiting, *chain])

    def _detect_cycle_in_list(self, chain: list[str]) -> None:
        seen: set[str] = set()
        path: list[str] = []
        for node in chain:
            if node in seen:
                raise CircularCompositionError([*path, node])
            seen.add(node)
            path.append(node)
