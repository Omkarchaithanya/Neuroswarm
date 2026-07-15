"""Fluent SwarmBuilder API."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ._utils import new_id
from .composer import SwarmComposer
from .constraints import SwarmConstraints
from .execution_profile import ExecutionProfile
from .lifecycle import LifecycleState
from .metadata import SwarmMetadata, normalize_labels, normalize_tags
from .models import SwarmRetryPolicy, TaskGraphReference
from .profile import SwarmProfile
from .template import SwarmTemplate


class SwarmBuilder:
    """Fluent builder for SwarmTemplate.

    Example::

        swarm = (
            SwarmBuilder()
            .template(id="nexus.swarms.custom", name="custom")
            .agents("nexus.agents.planning_agent", "nexus.agents.coding_agent")
            .context("request", "budget")
            .budget("envelope_id", "max_cost_usd")
            .build()
        )
    """

    def __init__(self) -> None:
        self._id: str | None = None
        self._name: str | None = None
        self._display_name: str = ""
        self._description: str = ""
        self._version: str = "1.0.0"
        self._category: str = "general"
        self._workflow_type: str = ""
        self._task_graph: TaskGraphReference = TaskGraphReference()
        self._required_agents: list[str] = []
        self._optional_agents: list[str] = []
        self._required_tools: list[str] = []
        self._required_models: list[str] = []
        self._required_backends: list[str] = []
        self._required_memory: list[str] = []
        self._required_context: list[str] = []
        self._required_budget: list[str] = []
        self._execution_profile: ExecutionProfile = ExecutionProfile()
        self._profile: SwarmProfile = SwarmProfile()
        self._constraints: SwarmConstraints = SwarmConstraints()
        self._estimated_cost: float = 0.0
        self._estimated_latency: float = 0.0
        self._estimated_memory: int = 0
        self._estimated_cpu: float = 0.0
        self._estimated_tokens: float = 0.0
        self._parallelism: int = 1
        self._priority: int = 50
        self._timeout: float | None = 300.0
        self._retry_policy: SwarmRetryPolicy = SwarmRetryPolicy()
        self._metadata: SwarmMetadata = SwarmMetadata()
        self._tags: list[str] = []
        self._labels: dict[str, str] = {}
        self._status: LifecycleState = LifecycleState.CREATED
        self._base: SwarmTemplate | None = None

    def template(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        display_name: str = "",
        description: str = "",
        version: str = "1.0.0",
        category: str = "general",
        workflow_type: str = "",
        base: SwarmTemplate | None = None,
    ) -> SwarmBuilder:
        if base is not None:
            self._base = base
            self._id = id or f"{base.id}.built"
            self._name = name or f"{base.name}_built"
            self._display_name = display_name or base.display_name
            self._description = description or base.description
            self._version = version or base.version
            self._category = category or base.category
            self._workflow_type = workflow_type or base.workflow_type
            self._task_graph = base.task_graph_reference
            self._required_agents = list(base.required_agents)
            self._optional_agents = list(base.optional_agents)
            self._required_tools = list(base.required_tools)
            self._required_models = list(base.required_models)
            self._required_backends = list(base.required_backends)
            self._required_memory = list(base.required_memory)
            self._required_context = list(base.required_context)
            self._required_budget = list(base.required_budget)
            self._execution_profile = base.execution_profile
            self._profile = base.profile
            self._constraints = base.constraints
            self._estimated_cost = base.estimated_cost
            self._estimated_latency = base.estimated_latency
            self._estimated_memory = base.estimated_memory
            self._estimated_cpu = base.estimated_cpu
            self._estimated_tokens = base.estimated_tokens
            self._parallelism = base.parallelism
            self._priority = base.priority
            self._timeout = base.timeout
            self._retry_policy = base.retry_policy
            self._metadata = base.metadata
            self._tags = list(base.tags)
            self._labels = dict(base.labels)
            return self
        self._id = id
        self._name = name
        self._display_name = display_name
        self._description = description
        self._version = version
        self._category = category
        self._workflow_type = workflow_type
        return self

    def agents(self, *agent_ids: str, optional: Sequence[str] | None = None) -> SwarmBuilder:
        self._required_agents = list(dict.fromkeys([*self._required_agents, *agent_ids]))
        if optional:
            self._optional_agents = list(
                dict.fromkeys([*self._optional_agents, *optional])
            )
        return self

    def tools(self, *tools: str) -> SwarmBuilder:
        self._required_tools = list(dict.fromkeys([*self._required_tools, *tools]))
        return self

    def models(self, *models: str) -> SwarmBuilder:
        self._required_models = list(dict.fromkeys([*self._required_models, *models]))
        return self

    def backends(self, *backends: str) -> SwarmBuilder:
        self._required_backends = list(
            dict.fromkeys([*self._required_backends, *backends])
        )
        return self

    def memory(self, *kinds: str) -> SwarmBuilder:
        self._required_memory = list(dict.fromkeys([*self._required_memory, *kinds]))
        return self

    def context(self, *keys: str) -> SwarmBuilder:
        self._required_context = list(dict.fromkeys([*self._required_context, *keys]))
        return self

    def budget(self, *keys: str) -> SwarmBuilder:
        self._required_budget = list(dict.fromkeys([*self._required_budget, *keys]))
        return self

    def task_graph(
        self,
        *,
        graph_id: str = "",
        graph_name: str = "",
        snapshot: Mapping[str, Any] | None = None,
        schema_version: int = 1,
    ) -> SwarmBuilder:
        self._task_graph = TaskGraphReference(
            graph_id=graph_id,
            graph_name=graph_name,
            schema_version=schema_version,
            snapshot=dict(snapshot) if snapshot else None,
        )
        return self

    def profile(self, profile: SwarmProfile) -> SwarmBuilder:
        self._profile = profile
        return self

    def execution(self, profile: ExecutionProfile) -> SwarmBuilder:
        self._execution_profile = profile
        return self

    def constraints(self, constraints: SwarmConstraints) -> SwarmBuilder:
        self._constraints = constraints
        return self

    def estimates(
        self,
        *,
        cost: float | None = None,
        latency: float | None = None,
        memory: int | None = None,
        cpu: float | None = None,
        tokens: float | None = None,
    ) -> SwarmBuilder:
        if cost is not None:
            self._estimated_cost = cost
        if latency is not None:
            self._estimated_latency = latency
        if memory is not None:
            self._estimated_memory = memory
        if cpu is not None:
            self._estimated_cpu = cpu
        if tokens is not None:
            self._estimated_tokens = tokens
        return self

    def parallelism(self, value: int) -> SwarmBuilder:
        self._parallelism = value
        return self

    def priority(self, value: int) -> SwarmBuilder:
        self._priority = value
        return self

    def timeout(self, seconds: float | None) -> SwarmBuilder:
        self._timeout = seconds
        return self

    def retry(self, policy: SwarmRetryPolicy) -> SwarmBuilder:
        self._retry_policy = policy
        return self

    def tags(self, *tags: str) -> SwarmBuilder:
        self._tags = normalize_tags([*self._tags, *tags])
        return self

    def labels(self, **labels: str) -> SwarmBuilder:
        self._labels = normalize_labels({**self._labels, **labels})
        return self

    def metadata(self, metadata: SwarmMetadata) -> SwarmBuilder:
        self._metadata = metadata
        return self

    def status(self, status: LifecycleState) -> SwarmBuilder:
        self._status = status
        return self

    def build(self) -> SwarmTemplate:
        tid = self._id or new_id("ss_")
        name = self._name or tid
        tpl = SwarmTemplate(
            id=tid,
            name=name,
            display_name=self._display_name,
            description=self._description,
            version=self._version,
            category=self._category,
            workflow_type=self._workflow_type,
            task_graph_reference=self._task_graph,
            required_agents=list(self._required_agents),
            optional_agents=list(self._optional_agents),
            required_tools=list(self._required_tools),
            required_models=list(self._required_models),
            required_backends=list(self._required_backends),
            required_memory=list(self._required_memory),
            required_context=list(self._required_context),
            required_budget=list(self._required_budget),
            execution_profile=self._execution_profile,
            profile=self._profile,
            constraints=self._constraints,
            estimated_cost=self._estimated_cost,
            estimated_latency=self._estimated_latency,
            estimated_memory=self._estimated_memory,
            estimated_cpu=self._estimated_cpu,
            estimated_tokens=self._estimated_tokens,
            parallelism=self._parallelism,
            priority=self._priority,
            timeout=self._timeout,
            retry_policy=self._retry_policy,
            metadata=self._metadata,
            tags=list(self._tags),
            labels=dict(self._labels),
            status=self._status,
        )
        if self._base is not None:
            composer = SwarmComposer()
            # ensure provenance tracks base
            return composer.extend(
                self._base,
                extra_agents=[
                    a for a in tpl.required_agents if a not in self._base.required_agents
                ],
                extra_tools=[
                    t for t in tpl.required_tools if t not in self._base.required_tools
                ],
                tags=tpl.tags,
                labels=tpl.labels,
                profile=tpl.profile,
                new_id=tpl.id,
                new_name=tpl.name,
            ).evolve(
                display_name=tpl.display_name or self._base.display_name,
                description=tpl.description or self._base.description,
                task_graph_reference=tpl.task_graph_reference
                if tpl.task_graph_reference.is_present
                else self._base.task_graph_reference,
                required_context=tpl.required_context or self._base.required_context,
                required_budget=tpl.required_budget or self._base.required_budget,
                estimated_cost=tpl.estimated_cost or self._base.estimated_cost,
                estimated_latency=tpl.estimated_latency or self._base.estimated_latency,
                estimated_memory=tpl.estimated_memory or self._base.estimated_memory,
                estimated_cpu=tpl.estimated_cpu or self._base.estimated_cpu,
                estimated_tokens=tpl.estimated_tokens or self._base.estimated_tokens,
                parallelism=tpl.parallelism,
                priority=tpl.priority,
                timeout=tpl.timeout,
                workflow_type=tpl.workflow_type or self._base.workflow_type,
                category=tpl.category or self._base.category,
            )
        return tpl
