"""ContextRequirementGraph IR — output of Understanding Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class RequirementKind(str, Enum):
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    TOOL = "tool"
    POLICY = "policy"
    WORKFLOW = "workflow"
    EXAMPLE = "example"
    REASONING = "reasoning"
    REFLECTION = "reflection"
    ENTITY = "entity"
    TOPIC = "topic"


@dataclass(slots=True)
class RequirementNode:
    """Single information need in the requirement graph."""

    id: str = field(default_factory=lambda: str(uuid4())[:12])
    kind: RequirementKind = RequirementKind.TOPIC
    label: str = ""
    entities: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    priority: float = 0.5
    must_have: bool = False
    token_estimate: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ContextRequirementGraph:
    """Compiler front-end IR: what information the task needs."""

    request_id: str
    intent: str = ""
    query: str = ""
    agent_role: str = "architect"
    workflow_class: str = "chat"
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    predicted_tools: list[str] = field(default_factory=list)
    nodes: list[RequirementNode] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (from_id, to_id) dependency
    metadata: dict = field(default_factory=dict)

    def must_have_nodes(self) -> list[RequirementNode]:
        return [n for n in self.nodes if n.must_have]

    def nodes_by_kind(self, kind: RequirementKind) -> list[RequirementNode]:
        return [n for n in self.nodes if n.kind == kind]
