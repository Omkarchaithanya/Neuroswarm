"""Planning IRs — RetrievalExecutionPlan, CompressionPlan, AssemblyPlan."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class RetrievalSource(str, Enum):
    MEMORY = "memory"
    OKF = "okf"
    TOOL_DOCS = "tool_docs"
    POLICY = "policy"
    WORKFLOW = "workflow"
    REASONING = "reasoning"
    REFLECTION = "reflection"
    EXAMPLES = "examples"


class CompressionPass(str, Enum):
    SEMANTIC_DEDUP = "semantic_dedup"
    TEMPORAL = "temporal"
    HIERARCHICAL = "hierarchical"
    IMPORTANCE_FILTER = "importance_filter"
    CONFLICT_RESOLVE = "conflict_resolve"
    REFERENCE = "reference"
    POINTER = "pointer"
    SECTION_FOLD = "section_fold"
    RELATIONSHIP = "relationship"
    PACK = "pack"
    CHUNK_MERGE = "chunk_merge"
    PROGRESSIVE = "progressive"


@dataclass(slots=True)
class RetrievalStep:
    id: str = field(default_factory=lambda: str(uuid4())[:12])
    source: RetrievalSource = RetrievalSource.MEMORY
    query: str = ""
    namespaces: list[str] = field(default_factory=list)
    limit: int = 5
    priority: float = 0.5
    token_budget: int = 400
    lazy: bool = False
    depends_on: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalExecutionPlan:
    """Retrieval DAG — what to load before compression/assembly."""

    plan_id: str = field(default_factory=lambda: str(uuid4())[:16])
    request_id: str = ""
    steps: list[RetrievalStep] = field(default_factory=list)
    token_budget: int = 2000
    latency_budget_ms: float = 200.0
    cost_budget: float = 0.01
    progressive: bool = True
    metadata: dict = field(default_factory=dict)

    def ordered_steps(self) -> list[RetrievalStep]:
        """Topological-ish order by depends_on then priority."""
        by_id = {s.id: s for s in self.steps}
        done: set[str] = set()
        ordered: list[RetrievalStep] = []
        remaining = list(self.steps)
        while remaining:
            progress = False
            for step in list(remaining):
                if all(d in done or d not in by_id for d in step.depends_on):
                    ordered.append(step)
                    done.add(step.id)
                    remaining.remove(step)
                    progress = True
            if not progress:
                # Cycle or missing deps — append by priority
                remaining.sort(key=lambda s: -s.priority)
                ordered.extend(remaining)
                break
        return ordered


@dataclass(slots=True)
class CompressionPlan:
    plan_id: str = field(default_factory=lambda: str(uuid4())[:12])
    passes: list[CompressionPass] = field(
        default_factory=lambda: [
            CompressionPass.SEMANTIC_DEDUP,
            CompressionPass.IMPORTANCE_FILTER,
            CompressionPass.TEMPORAL,
            CompressionPass.HIERARCHICAL,
            CompressionPass.CONFLICT_RESOLVE,
            CompressionPass.REFERENCE,
            CompressionPass.SECTION_FOLD,
            CompressionPass.PACK,
            CompressionPass.CHUNK_MERGE,
            CompressionPass.PROGRESSIVE,
        ]
    )
    token_budget: int = 2000
    min_importance: float = 0.2
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class AssemblyPlan:
    plan_id: str = field(default_factory=lambda: str(uuid4())[:12])
    section_order: list[str] = field(
        default_factory=lambda: [
            "instructions",
            "policies",
            "knowledge",
            "memories",
            "reflections",
            "reasoning",
            "tools",
            "examples",
            "workflows",
        ]
    )
    token_budget: int = 2000
    stable_prefix: bool = True  # prompt-cache friendly
    include_citations: bool = True
    metadata: dict = field(default_factory=dict)
