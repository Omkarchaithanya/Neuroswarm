"""Built-in agent profiles for NEXUS-ARM."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from .agent import Agent
from .capability import AgentCapability
from .lifecycle import LifecycleState
from .models import ExecutionLimits, ResourceRequirements

if TYPE_CHECKING:
    from .registry import AgentRegistry


def _base_caps(**kwargs: object) -> AgentCapability:
    return AgentCapability.model_validate(kwargs)


def research_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["research", "synthesis", "web_search"],
        supported_workflows=["chat", "multi_agent"],
        supported_tools=["nexus.tools.web_search", "nexus.tools.github"],
        supported_models=["qwen2.5-3b", "qwen2.5-8b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q4_k_m", "q5_k_m"],
        supported_embeddings=["bge-small"],
        supported_memory=["session", "okf"],
        supported_languages=["en"],
        supports_streaming=True,
        supports_reasoning=True,
        supports_planning=False,
        supports_parallel=True,
        supports_checkpoint=True,
        supports_retry=True,
        max_context=16384,
        max_tokens=4096,
        preferred_models=["qwen2.5-3b"],
        preferred_tools=["nexus.tools.web_search"],
        preferred_quantization="q5_k_m",
        preferred_backend="cascade",
    )
    return Agent(
        id="nexus.agents.research_analyst",
        name="research_agent",
        display_name="Research Agent",
        description="Long-form synthesis across web and code sources",
        version="1.0.0",
        agent_type="research",
        category="research",
        status=LifecycleState.CREATED,
        priority=80,
        owner="platform-team",
        tags=["agent", "research", "synthesis"],
        capabilities=caps,
        estimated_latency=2500.0,
        estimated_cost=0.004,
        estimated_tokens=1200.0,
        estimated_memory=512 * 1024 * 1024,
        estimated_cpu=4.0,
        estimated_threads=8,
        confidence_score=0.85,
        resource_requirements=ResourceRequirements(
            memory_bytes=512 * 1024 * 1024,
            cpu_cores=4.0,
            threads=8,
            estimated_cost=0.004,
            estimated_latency_ms=2500.0,
            estimated_tokens=1200.0,
        ),
        execution_limits=ExecutionLimits(max_concurrent=4, timeout_s=120.0),
        streaming_support=True,
        checkpoint_support=True,
        parallel_support=True,
        future_distributed_support=True,
    )


def coding_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["coding", "implementation", "refactor"],
        supported_workflows=["chat", "multi_agent"],
        supported_tools=["nexus.tools.github"],
        supported_models=["qwen2.5-3b", "qwen2.5-8b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q4_k_m", "q5_k_m", "q8_0"],
        supported_memory=["session", "repo"],
        supported_languages=["python", "typescript", "go", "rust"],
        supported_file_types=[".py", ".ts", ".go", ".rs", ".md"],
        supports_streaming=True,
        supports_reasoning=True,
        supports_parallel=False,
        supports_checkpoint=True,
        supports_retry=True,
        max_context=32768,
        max_tokens=8192,
        preferred_models=["qwen2.5-8b"],
        preferred_tools=["nexus.tools.github"],
        preferred_quantization="q5_k_m",
        preferred_backend="llama.cpp",
    )
    return Agent(
        id="nexus.agents.coding_agent",
        name="coding_agent",
        display_name="Coding Agent",
        description="Implementation and repository navigation agent",
        version="1.0.0",
        agent_type="coding",
        category="coding",
        priority=75,
        owner="platform-team",
        tags=["agent", "coding"],
        capabilities=caps,
        estimated_latency=3000.0,
        estimated_cost=0.006,
        estimated_tokens=2000.0,
        estimated_memory=768 * 1024 * 1024,
        estimated_cpu=6.0,
        estimated_threads=12,
        confidence_score=0.88,
        streaming_support=True,
        checkpoint_support=True,
    )


def planning_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["planning", "decomposition", "scheduling"],
        supported_workflows=["chat", "multi_agent", "task_graph"],
        supported_tools=[],
        supported_models=["qwen2.5-3b", "qwen2.5-0.5b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q4_k_m", "q5_k_m"],
        supported_memory=["session", "okf"],
        supports_streaming=True,
        supports_reasoning=True,
        supports_planning=True,
        supports_parallel=True,
        supports_checkpoint=True,
        max_context=16384,
        max_tokens=4096,
        preferred_models=["qwen2.5-3b"],
        preferred_quantization="q4_k_m",
        preferred_backend="cascade",
    )
    return Agent(
        id="nexus.agents.planning_agent",
        name="planning_agent",
        display_name="Planning Agent",
        description="Task decomposition and execution planning",
        version="1.0.0",
        agent_type="planning",
        category="planning",
        priority=85,
        tags=["agent", "planning"],
        capabilities=caps,
        estimated_latency=1500.0,
        estimated_cost=0.002,
        estimated_tokens=800.0,
        estimated_memory=256 * 1024 * 1024,
        confidence_score=0.9,
        streaming_support=True,
        parallel_support=True,
        checkpoint_support=True,
    )


def reviewer_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["review", "critique", "verification"],
        supported_workflows=["chat", "multi_agent"],
        supported_tools=["nexus.tools.github"],
        supported_models=["qwen2.5-3b", "qwen2.5-8b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q5_k_m", "q8_0"],
        supports_streaming=True,
        supports_reasoning=True,
        supports_review=True,
        supports_checkpoint=False,
        max_context=16384,
        max_tokens=4096,
        preferred_models=["qwen2.5-8b"],
        preferred_quantization="q5_k_m",
        preferred_backend="llama.cpp",
    )
    return Agent(
        id="nexus.agents.reviewer_agent",
        name="reviewer_agent",
        display_name="Reviewer Agent",
        description="Code and plan review / verification",
        version="1.0.0",
        agent_type="reviewer",
        category="review",
        priority=70,
        tags=["agent", "review"],
        capabilities=caps,
        estimated_latency=2000.0,
        estimated_cost=0.003,
        estimated_tokens=1000.0,
        confidence_score=0.87,
        streaming_support=True,
    )


def memory_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["memory", "recall", "summarize_context"],
        supported_workflows=["chat", "memory"],
        supported_tools=[],
        supported_models=["qwen2.5-0.5b", "qwen2.5-3b"],
        supported_backends=["llama.cpp"],
        supported_quantizations=["q4_k_m", "q4_0"],
        supported_memory=["session", "mem0", "okf", "kv"],
        supports_streaming=False,
        supports_reasoning=False,
        supports_checkpoint=True,
        supports_resume=True,
        max_context=8192,
        max_tokens=2048,
        preferred_models=["qwen2.5-0.5b"],
        preferred_quantization="q4_k_m",
        preferred_backend="llama.cpp",
    )
    return Agent(
        id="nexus.agents.memory_agent",
        name="memory_agent",
        display_name="Memory Agent",
        description="Session and long-term memory operations",
        version="1.0.0",
        agent_type="memory",
        category="memory",
        priority=60,
        tags=["agent", "memory"],
        capabilities=caps,
        estimated_latency=400.0,
        estimated_cost=0.0005,
        estimated_tokens=300.0,
        estimated_memory=128 * 1024 * 1024,
        confidence_score=0.92,
        checkpoint_support=True,
    )


def tool_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["tool_use", "mcp", "function_call"],
        supported_workflows=["chat", "tool_route"],
        supported_tools=["nexus.tools.web_search", "nexus.tools.github"],
        supported_models=["qwen2.5-0.5b", "qwen2.5-3b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q4_k_m"],
        supports_streaming=True,
        supports_parallel=True,
        supports_retry=True,
        max_context=8192,
        max_tokens=2048,
        preferred_models=["qwen2.5-0.5b"],
        preferred_tools=["nexus.tools.web_search"],
        preferred_quantization="q4_k_m",
        preferred_backend="cascade",
    )
    return Agent(
        id="nexus.agents.tool_agent",
        name="tool_agent",
        display_name="Tool Agent",
        description="MCP / tool invocation specialist",
        version="1.0.0",
        agent_type="tool",
        category="tools",
        priority=65,
        tags=["agent", "tools", "mcp"],
        capabilities=caps,
        estimated_latency=800.0,
        estimated_cost=0.001,
        estimated_tokens=400.0,
        confidence_score=0.86,
        streaming_support=True,
        parallel_support=True,
    )


def router_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["routing", "classification", "triage"],
        supported_workflows=["chat", "cascade"],
        supported_models=["qwen2.5-0.5b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q4_0", "q4_k_m"],
        supports_streaming=False,
        supports_reasoning=False,
        supports_parallel=True,
        max_context=4096,
        max_tokens=512,
        preferred_models=["qwen2.5-0.5b"],
        preferred_quantization="q4_0",
        preferred_backend="cascade",
    )
    return Agent(
        id="nexus.agents.router_agent",
        name="router_agent",
        display_name="Router Agent",
        description="Fast triage and cascade tier routing",
        version="1.0.0",
        agent_type="router",
        category="routing",
        priority=90,
        tags=["agent", "router", "cascade"],
        capabilities=caps,
        estimated_latency=120.0,
        estimated_cost=0.0001,
        estimated_tokens=64.0,
        estimated_memory=64 * 1024 * 1024,
        confidence_score=0.8,
        parallel_support=True,
    )


def evaluator_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["evaluation", "scoring", "acceptance"],
        supported_workflows=["multi_agent", "verification"],
        supported_models=["qwen2.5-3b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q5_k_m"],
        supports_streaming=False,
        supports_reasoning=True,
        supports_review=True,
        supports_metrics=True,
        supports_cost_tracking=True,
        max_context=8192,
        max_tokens=2048,
        preferred_models=["qwen2.5-3b"],
        preferred_quantization="q5_k_m",
        preferred_backend="llama.cpp",
    )
    return Agent(
        id="nexus.agents.evaluator_agent",
        name="evaluator_agent",
        display_name="Evaluator Agent",
        description="Output quality and acceptance scoring",
        version="1.0.0",
        agent_type="evaluator",
        category="evaluation",
        priority=72,
        tags=["agent", "evaluation"],
        capabilities=caps,
        estimated_latency=900.0,
        estimated_cost=0.0015,
        estimated_tokens=500.0,
        confidence_score=0.84,
    )


def summarizer_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["summarization", "compression", "digest"],
        supported_workflows=["chat", "memory", "acr"],
        supported_models=["qwen2.5-0.5b", "qwen2.5-3b"],
        supported_backends=["llama.cpp"],
        supported_quantizations=["q4_k_m", "q4_0"],
        supported_memory=["session", "acr"],
        supports_streaming=True,
        supports_checkpoint=False,
        max_context=16384,
        max_tokens=2048,
        preferred_models=["qwen2.5-0.5b"],
        preferred_quantization="q4_0",
        preferred_backend="llama.cpp",
    )
    return Agent(
        id="nexus.agents.summarizer_agent",
        name="summarizer_agent",
        display_name="Summarizer Agent",
        description="Context summarization and compression",
        version="1.0.0",
        agent_type="summarizer",
        category="compression",
        priority=55,
        tags=["agent", "summarization"],
        capabilities=caps,
        estimated_latency=600.0,
        estimated_cost=0.0008,
        estimated_tokens=400.0,
        confidence_score=0.89,
        streaming_support=True,
    )


def coordinator_agent() -> Agent:
    caps = _base_caps(
        supported_tasks=["coordination", "orchestration", "swarm"],
        supported_workflows=["multi_agent", "task_graph", "swarm"],
        supported_models=["qwen2.5-3b"],
        supported_backends=["llama.cpp", "cascade"],
        supported_quantizations=["q5_k_m"],
        supported_memory=["session", "swarm"],
        supports_streaming=True,
        supports_reasoning=True,
        supports_planning=True,
        supports_parallel=True,
        supports_checkpoint=True,
        supports_resume=True,
        max_context=16384,
        max_tokens=4096,
        preferred_models=["qwen2.5-3b"],
        preferred_quantization="q5_k_m",
        preferred_backend="cascade",
    )
    return Agent(
        id="nexus.agents.coordinator_agent",
        name="coordinator_agent",
        display_name="Coordinator Agent",
        description="Multi-agent swarm coordination",
        version="1.0.0",
        agent_type="coordinator",
        category="orchestration",
        priority=95,
        tags=["agent", "coordinator", "swarm"],
        capabilities=caps,
        estimated_latency=1800.0,
        estimated_cost=0.0035,
        estimated_tokens=900.0,
        confidence_score=0.91,
        streaming_support=True,
        parallel_support=True,
        checkpoint_support=True,
        future_distributed_support=True,
    )


BUILTIN_PROFILE_FACTORIES: dict[str, Callable[[], Agent]] = {
    "research_agent": research_agent,
    "coding_agent": coding_agent,
    "planning_agent": planning_agent,
    "reviewer_agent": reviewer_agent,
    "memory_agent": memory_agent,
    "tool_agent": tool_agent,
    "router_agent": router_agent,
    "evaluator_agent": evaluator_agent,
    "summarizer_agent": summarizer_agent,
    "coordinator_agent": coordinator_agent,
}


def all_builtin_profiles() -> list[Agent]:
    return [factory() for factory in BUILTIN_PROFILE_FACTORIES.values()]


def register_builtin_profiles(
    registry: AgentRegistry,
    *,
    replace_existing: bool = True,
) -> int:
    """Register all built-in profiles. Returns count registered."""
    return registry.bulk_register(
        all_builtin_profiles(),
        replace_existing=replace_existing,
    )
