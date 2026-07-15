"""ContextSnapshot / Version / Assembly output IRs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from neuroswarm_arm.runtime.acr.ir.stats import ContextStatistics


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ProvenanceRef:
    kind: str  # memory | okf | tool_docs | policy | plan
    ref_id: str
    path: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AssembledSection:
    name: str
    text: str
    priority: float = 0.5
    tokens: int = 0
    citations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FinalStructuredPrompt:
    text: str
    sections: list[AssembledSection] = field(default_factory=list)
    token_count: int = 0


@dataclass(slots=True)
class ContextVersion:
    version_id: str = field(default_factory=lambda: str(uuid4())[:16])
    content_hash: str = ""
    parent_id: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    lineage: list[str] = field(default_factory=list)
    build_history: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextGraph:
    """Lightweight graph of assembled context nodes for scoring/debug."""

    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # from, to, rel


@dataclass(slots=True)
class ContextSnapshot:
    """Reproducible assembled context — linker output."""

    request_id: str
    plan_id: str = ""
    version: ContextVersion = field(default_factory=ContextVersion)
    prompt: str = ""
    sections: list[AssembledSection] = field(default_factory=list)
    provenance: list[ProvenanceRef] = field(default_factory=list)
    stats: ContextStatistics = field(default_factory=ContextStatistics)
    graph: ContextGraph = field(default_factory=ContextGraph)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_count(self) -> int:
        return self.stats.output_tokens or max(1, len(self.prompt.split()))
