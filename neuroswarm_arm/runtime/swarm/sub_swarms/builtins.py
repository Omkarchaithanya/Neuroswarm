"""Built-in production Sub Swarm templates (Task Graph references only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from neuroswarm_arm.runtime.swarm.task_graph.builders import TaskGraphBuilder
from neuroswarm_arm.runtime.swarm.task_graph.enums import NodeType, Priority

from .capabilities import SwarmCapability
from .constraints import SwarmConstraints
from .execution_profile import ExecutionProfile
from .lifecycle import LifecycleState
from .metadata import SwarmMetadata
from .models import SwarmRetryPolicy, TaskGraphReference
from .profile import (
    BackendProfile,
    BudgetProfile,
    ContextProfile,
    CostProfile,
    LatencyProfile,
    MemoryProfile,
    ModelProfile,
    ResourceProfile,
    SwarmProfile,
)
from .template import SwarmTemplate

if TYPE_CHECKING:
    from .registry import SubSwarmRegistry

# Agent Registry ids (string refs only — no execution)
RESEARCH = "nexus.agents.research_analyst"
CODING = "nexus.agents.coding_agent"
PLANNING = "nexus.agents.planning_agent"
REVIEWER = "nexus.agents.reviewer_agent"
MEMORY = "nexus.agents.memory_agent"
TOOL = "nexus.agents.tool_agent"
EVALUATOR = "nexus.agents.evaluator_agent"
SUMMARIZER = "nexus.agents.summarizer_agent"
WRITER = "nexus.agents.writer_agent"
TESTER = "nexus.agents.evaluator_agent"
EXECUTOR = "nexus.agents.tool_agent"
METRICS_AGENT = "nexus.agents.evaluator_agent"


def _graph_ref(graph_name: str, builder: TaskGraphBuilder) -> TaskGraphReference:
    graph = builder.build(validate=True)
    snapshot = graph.model_dump(mode="json")
    return TaskGraphReference(
        graph_id=graph.graph_id or graph_name,
        graph_name=graph_name or graph.name,
        schema_version=1,
        snapshot=snapshot,
    )


def _base_profile(
    *,
    cost: float,
    latency: float,
    memory: int,
    cpu: float,
    tokens: float,
    models: list[str],
    backends: list[str],
    memory_kinds: list[str],
    context_keys: list[str],
    parallelism: int = 1,
    priority: int = 70,
) -> SwarmProfile:
    return SwarmProfile(
        resource=ResourceProfile(
            memory_bytes=memory, cpu_cores=cpu, threads=max(1, int(cpu))
        ),
        budget=BudgetProfile(max_cost_usd=cost * 2, max_tokens=tokens * 2),
        execution=ExecutionProfile(
            parallelism=parallelism,
            priority=priority,
            timeout_s=300.0,
            retry_policy=SwarmRetryPolicy(max_attempts=3),
            execution_policy="hybrid",
        ),
        latency=LatencyProfile(target_ms=latency, timeout_ms=latency * 2),
        cost=CostProfile(estimated_usd=cost, max_usd=cost * 2),
        memory=MemoryProfile(kinds=memory_kinds, max_bytes=memory),
        model=ModelProfile(preferred_models=models, allowed_models=models),
        backend=BackendProfile(
            preferred_backend=backends[0] if backends else "",
            allowed_backends=backends,
        ),
        context=ContextProfile(required_keys=context_keys, defaults={}),
    )


def _template(
    *,
    id: str,
    name: str,
    display_name: str,
    description: str,
    category: str,
    workflow_type: str,
    graph: TaskGraphReference,
    agents: list[str],
    tools: list[str],
    models: list[str],
    backends: list[str],
    memory_kinds: list[str],
    context_keys: list[str],
    budget_keys: list[str],
    capabilities: list[str],
    tasks: list[str],
    cost: float,
    latency: float,
    memory: int,
    cpu: float,
    tokens: float,
    parallelism: int = 1,
    priority: int = 70,
    optional_agents: list[str] | None = None,
) -> SwarmTemplate:
    unique_agents = list(dict.fromkeys(agents))
    return SwarmTemplate(
        id=id,
        name=name,
        display_name=display_name,
        description=description,
        version="1.0.0",
        category=category,
        workflow_type=workflow_type,
        task_graph_reference=graph,
        required_agents=unique_agents,
        optional_agents=list(dict.fromkeys(optional_agents or [])),
        required_tools=tools,
        required_models=models,
        required_backends=backends,
        required_memory=memory_kinds,
        required_context=context_keys,
        required_budget=budget_keys,
        execution_profile=ExecutionProfile(
            parallelism=parallelism,
            priority=priority,
            timeout_s=300.0,
            execution_policy="hybrid" if parallelism > 1 else "sequential",
        ),
        profile=_base_profile(
            cost=cost,
            latency=latency,
            memory=memory,
            cpu=cpu,
            tokens=tokens,
            models=models,
            backends=backends,
            memory_kinds=memory_kinds,
            context_keys=context_keys,
            parallelism=parallelism,
            priority=priority,
        ),
        capabilities=SwarmCapability(
            required_capabilities=capabilities,
            supported_tasks=tasks,
            supported_workflows=[workflow_type, "multi_agent"],
            min_agents=len(unique_agents),
            supports_parallel=parallelism > 1,
        ),
        constraints=SwarmConstraints(
            min_agents=len(unique_agents),
            required_capabilities=capabilities[:1],
            required_tools=tools,
            required_models=models[:1] if models else [],
            required_backends=backends[:1] if backends else [],
            required_memory=memory_kinds,
            required_context=context_keys,
            required_budget_keys=budget_keys,
            max_cost_usd=max(cost * 4, 0.05),
            max_latency_ms=max(latency * 4, 30_000.0),
            max_memory_bytes=memory * 2,
            max_cpu_cores=cpu * 2,
            max_tokens=tokens * 3,
        ),
        estimated_cost=cost,
        estimated_latency=latency,
        estimated_memory=memory,
        estimated_cpu=cpu,
        estimated_tokens=tokens,
        parallelism=parallelism,
        priority=priority,
        timeout=300.0,
        retry_policy=SwarmRetryPolicy(max_attempts=3),
        metadata=SwarmMetadata(owner="platform-team", source="builtin"),
        tags=["swarm", category, "builtin"],
        labels={"nexus.swarm.kind": category},
        status=LifecycleState.CREATED,
    )


def research_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="research_swarm")
        .task(
            "research",
            node_type=NodeType.AGENT,
            agent_type="research",
            priority=Priority.HIGH,
        )
        .task("memory", node_type=NodeType.MEMORY, agent_type="memory")
        .task("review", node_type=NodeType.AGENT, agent_type="reviewer")
    )
    return _template(
        id="nexus.swarms.research",
        name="research_swarm",
        display_name="Research Swarm",
        description="Research synthesis with memory grounding and review",
        category="research",
        workflow_type="research",
        graph=_graph_ref("research_swarm", b),
        agents=[RESEARCH, MEMORY, REVIEWER],
        tools=["nexus.tools.web_search"],
        models=["qwen2.5-3b", "qwen2.5-8b"],
        backends=["cascade", "llama.cpp"],
        memory_kinds=["session", "okf"],
        context_keys=["request", "budget"],
        budget_keys=["envelope_id", "max_cost_usd"],
        capabilities=["research", "synthesis", "review"],
        tasks=["research", "synthesis"],
        cost=0.012,
        latency=8000.0,
        memory=1024 * 1024 * 1024,
        cpu=6.0,
        tokens=4000.0,
        priority=75,
    )


def coding_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="coding_swarm")
        .task("planner", node_type=NodeType.AGENT, agent_type="planning", priority=Priority.HIGH)
        .task("coder", node_type=NodeType.AGENT, agent_type="coding")
        .task("tester", node_type=NodeType.AGENT, agent_type="evaluator")
        .task("review", node_type=NodeType.AGENT, agent_type="reviewer")
    )
    return _template(
        id="nexus.swarms.coding",
        name="coding_swarm",
        display_name="Coding Swarm",
        description="Plan, implement, test, and review code changes",
        category="coding",
        workflow_type="coding",
        graph=_graph_ref("coding_swarm", b),
        agents=[PLANNING, CODING, TESTER, REVIEWER],
        tools=["nexus.tools.github"],
        models=["qwen2.5-8b"],
        backends=["llama.cpp", "cascade"],
        memory_kinds=["session", "repo"],
        context_keys=["request", "budget", "repo"],
        budget_keys=["envelope_id", "max_cost_usd"],
        capabilities=["planning", "coding", "testing", "review"],
        tasks=["coding", "implementation", "refactor"],
        cost=0.02,
        latency=12000.0,
        memory=1536 * 1024 * 1024,
        cpu=8.0,
        tokens=8000.0,
        priority=80,
    )


def documentation_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="documentation_swarm")
        .task("research", node_type=NodeType.AGENT, agent_type="research")
        .task("summarize", node_type=NodeType.AGENT, agent_type="summarizer")
        .task("write", node_type=NodeType.AGENT, agent_type="summarizer")
        .task("review", node_type=NodeType.AGENT, agent_type="reviewer")
    )
    return _template(
        id="nexus.swarms.documentation",
        name="documentation_swarm",
        display_name="Documentation Swarm",
        description="Research, summarize, write, and review documentation",
        category="documentation",
        workflow_type="documentation",
        graph=_graph_ref("documentation_swarm", b),
        agents=[RESEARCH, SUMMARIZER, WRITER, REVIEWER],
        tools=["nexus.tools.web_search", "nexus.tools.github"],
        models=["qwen2.5-3b", "qwen2.5-8b"],
        backends=["cascade", "llama.cpp"],
        memory_kinds=["session", "okf"],
        context_keys=["request", "budget"],
        budget_keys=["envelope_id"],
        capabilities=["research", "summarization", "writing", "review"],
        tasks=["documentation", "summarization"],
        cost=0.01,
        latency=9000.0,
        memory=768 * 1024 * 1024,
        cpu=4.0,
        tokens=5000.0,
        priority=65,
    )


def tool_execution_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="tool_execution_swarm")
        .task("planner", node_type=NodeType.AGENT, agent_type="planning", priority=Priority.HIGH)
        .task("tool", node_type=NodeType.AGENT, agent_type="tool")
        .task("memory", node_type=NodeType.MEMORY, agent_type="memory")
        .task("review", node_type=NodeType.AGENT, agent_type="reviewer")
    )
    return _template(
        id="nexus.swarms.tool_execution",
        name="tool_execution_swarm",
        display_name="Tool Execution Swarm",
        description="Plan tool use, execute tools, persist memory, review",
        category="tools",
        workflow_type="tool_execution",
        graph=_graph_ref("tool_execution_swarm", b),
        agents=[PLANNING, TOOL, MEMORY, REVIEWER],
        tools=["nexus.tools.web_search", "nexus.tools.github"],
        models=["qwen2.5-3b"],
        backends=["cascade", "llama.cpp"],
        memory_kinds=["session"],
        context_keys=["request", "budget", "tools"],
        budget_keys=["envelope_id", "max_cost_usd"],
        capabilities=["planning", "tool_use", "memory", "review"],
        tasks=["tool_execution", "planning"],
        cost=0.015,
        latency=10000.0,
        memory=1024 * 1024 * 1024,
        cpu=6.0,
        tokens=3500.0,
        priority=70,
    )


def analysis_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="analysis_swarm")
        .task("planner", node_type=NodeType.AGENT, agent_type="planning", priority=Priority.HIGH)
        .parallel("research", "memory", agent_type="worker")
        .task("evaluate", node_type=NodeType.AGENT, agent_type="evaluator")
    )
    return _template(
        id="nexus.swarms.analysis",
        name="analysis_swarm",
        display_name="Analysis Swarm",
        description="Plan analysis with parallel research/memory then evaluate",
        category="analysis",
        workflow_type="analysis",
        graph=_graph_ref("analysis_swarm", b),
        agents=[PLANNING, RESEARCH, MEMORY, EVALUATOR],
        tools=["nexus.tools.web_search"],
        models=["qwen2.5-8b"],
        backends=["cascade"],
        memory_kinds=["session", "okf"],
        context_keys=["request", "budget"],
        budget_keys=["envelope_id"],
        capabilities=["planning", "research", "memory", "evaluation"],
        tasks=["analysis", "evaluation"],
        cost=0.018,
        latency=11000.0,
        memory=1280 * 1024 * 1024,
        cpu=8.0,
        tokens=6000.0,
        parallelism=2,
        priority=72,
    )


def planning_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="planning_swarm")
        .task("planner", node_type=NodeType.AGENT, agent_type="planning", priority=Priority.HIGH)
        .task("research", node_type=NodeType.AGENT, agent_type="research")
        .task("review", node_type=NodeType.AGENT, agent_type="reviewer")
    )
    return _template(
        id="nexus.swarms.planning",
        name="planning_swarm",
        display_name="Planning Swarm",
        description="Plan with research grounding and review",
        category="planning",
        workflow_type="planning",
        graph=_graph_ref("planning_swarm", b),
        agents=[PLANNING, RESEARCH, REVIEWER],
        tools=["nexus.tools.web_search"],
        models=["qwen2.5-3b", "qwen2.5-8b"],
        backends=["cascade", "llama.cpp"],
        memory_kinds=["session"],
        context_keys=["request", "budget"],
        budget_keys=["envelope_id"],
        capabilities=["planning", "research", "review"],
        tasks=["planning", "decomposition"],
        cost=0.008,
        latency=6000.0,
        memory=512 * 1024 * 1024,
        cpu=4.0,
        tokens=2500.0,
        priority=78,
    )


def benchmark_swarm() -> SwarmTemplate:
    b = (
        TaskGraphBuilder(name="benchmark_swarm")
        .task("planner", node_type=NodeType.AGENT, agent_type="planning", priority=Priority.HIGH)
        .task("execute", node_type=NodeType.TASK, agent_type="tool", handler_key="benchmark_execute")
        .task("metrics", node_type=NodeType.TASK, agent_type="evaluator", handler_key="benchmark_metrics")
        .task("review", node_type=NodeType.AGENT, agent_type="reviewer")
    )
    return _template(
        id="nexus.swarms.benchmark",
        name="benchmark_swarm",
        display_name="Benchmark Swarm",
        description="Plan, execute, collect metrics, and review benchmarks",
        category="benchmark",
        workflow_type="benchmark",
        graph=_graph_ref("benchmark_swarm", b),
        agents=[PLANNING, EXECUTOR, METRICS_AGENT, REVIEWER],
        tools=["nexus.tools.github"],
        models=["qwen2.5-3b"],
        backends=["llama.cpp", "cascade"],
        memory_kinds=["session"],
        context_keys=["request", "budget", "benchmark"],
        budget_keys=["envelope_id", "max_cost_usd"],
        capabilities=["planning", "execution", "metrics", "review"],
        tasks=["benchmark", "evaluation"],
        cost=0.025,
        latency=20000.0,
        memory=2048 * 1024 * 1024,
        cpu=10.0,
        tokens=3000.0,
        priority=60,
    )


BUILTIN_TEMPLATE_FACTORIES: dict[str, Callable[[], SwarmTemplate]] = {
    "nexus.swarms.research": research_swarm,
    "nexus.swarms.coding": coding_swarm,
    "nexus.swarms.documentation": documentation_swarm,
    "nexus.swarms.tool_execution": tool_execution_swarm,
    "nexus.swarms.analysis": analysis_swarm,
    "nexus.swarms.planning": planning_swarm,
    "nexus.swarms.benchmark": benchmark_swarm,
}


def all_builtin_templates() -> list[SwarmTemplate]:
    return [factory() for factory in BUILTIN_TEMPLATE_FACTORIES.values()]


def register_builtin_templates(
    registry: SubSwarmRegistry,
    *,
    promote_to_ready: bool = True,
) -> list[SwarmTemplate]:
    """Register all built-in templates into ``registry``."""
    registered: list[SwarmTemplate] = []
    for factory in BUILTIN_TEMPLATE_FACTORIES.values():
        tpl = factory()
        record = registry.register(tpl, promote_to=LifecycleState.REGISTERED)
        if promote_to_ready:
            record = registry.set_status(record.id, LifecycleState.READY)
        registered.append(record)
    return registered
