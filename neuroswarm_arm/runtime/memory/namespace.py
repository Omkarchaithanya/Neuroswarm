"""Namespace helpers for cognitive memory isolation."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.exceptions import MemoryNamespaceError
from neuroswarm_arm.runtime.memory.schemas import MemoryType

# Canonical namespace roots (trailing slash required).
NAMESPACES: frozenset[str] = frozenset(
    {
        "users/",
        "agents/",
        "workflows/",
        "tools/",
        "benchmarks/",
        "prompts/",
        "system/",
        "swarm/",
        "reflection/",
        "reasoning/",
        "performance/",
        "cost/",
        "planner/",
        "router/",
        "execution/",
        "latency/",
        "evolution/",
    }
)

_TYPE_TO_NS: dict[MemoryType, str] = {
    MemoryType.USER: "users/",
    MemoryType.AGENT: "agents/",
    MemoryType.EXECUTION: "execution/",
    MemoryType.WORKFLOW: "workflows/",
    MemoryType.TOOL: "tools/",
    MemoryType.REASONING: "reasoning/",
    MemoryType.REFLECTION: "reflection/",
    MemoryType.EXPERIENCE: "agents/",
    MemoryType.PERFORMANCE: "performance/",
    MemoryType.BENCHMARK: "benchmarks/",
    MemoryType.COST: "cost/",
    MemoryType.LATENCY: "latency/",
    MemoryType.FAILURE: "execution/",
    MemoryType.SUCCESS: "execution/",
    MemoryType.PROMPT: "prompts/",
    MemoryType.EVOLUTION: "evolution/",
    MemoryType.PLANNING: "planner/",
    MemoryType.SWARM: "swarm/",
    MemoryType.SYSTEM: "system/",
    MemoryType.FACT: "agents/",
}


def normalize_namespace(namespace: str) -> str:
    ns = (namespace or "").strip().replace("\\", "/")
    if not ns:
        raise MemoryNamespaceError("namespace empty")
    if not ns.endswith("/"):
        ns = f"{ns}/"
    root = ns.split("/", 1)[0] + "/"
    if root not in NAMESPACES:
        raise MemoryNamespaceError(f"unknown namespace root: {root}")
    return ns


def namespace_for_type(memory_type: MemoryType | str) -> str:
    if isinstance(memory_type, str):
        memory_type = MemoryType(memory_type)
    return _TYPE_TO_NS.get(memory_type, "agents/")


def scope_key(namespace: str, owner: str) -> str:
    return f"{normalize_namespace(namespace)}{owner}"


def parse_scope(scope: str) -> tuple[str, str]:
    """Split ``namespace/owner`` or ``namespace/subdir/owner`` → (namespace, owner)."""
    parts = scope.strip("/").split("/")
    if len(parts) < 2:
        raise MemoryNamespaceError(f"invalid scope: {scope}")
    owner = parts[-1]
    ns = "/".join(parts[:-1]) + "/"
    return normalize_namespace(ns), owner
