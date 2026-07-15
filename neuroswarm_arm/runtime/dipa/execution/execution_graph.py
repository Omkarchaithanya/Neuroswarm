"""Execution graph produced by the planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


LIFECYCLE_NODES = [
    "classify",
    "intent",
    "route_model",
    "route_backend",
    "probe_hardware",
    "apply_policy",
    "resolve_quant",
    "check_warm",
    "attach_kv",
    "cascade_or_direct",
    "prefill",
    "decode",
    "stream",
    "save_kv",
    "emit_metrics",
]


@dataclass
class GraphNode:
    name: str
    fn: Callable[..., Any] | None = None
    deps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionGraph:
    nodes: list[GraphNode] = field(default_factory=list)

    @classmethod
    def default_lifecycle(cls) -> ExecutionGraph:
        nodes: list[GraphNode] = []
        prev: str | None = None
        for name in LIFECYCLE_NODES:
            deps = [prev] if prev else []
            nodes.append(GraphNode(name=name, deps=deps))
            prev = name
        return cls(nodes=nodes)

    def names(self) -> list[str]:
        return [n.name for n in self.nodes]
