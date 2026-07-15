"""Typed memory schemas for the Cognitive Memory Runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryType(str, Enum):
    USER = "user"
    AGENT = "agent"
    EXECUTION = "execution"
    WORKFLOW = "workflow"
    TOOL = "tool"
    REASONING = "reasoning"
    REFLECTION = "reflection"
    EXPERIENCE = "experience"
    PERFORMANCE = "performance"
    BENCHMARK = "benchmark"
    COST = "cost"
    LATENCY = "latency"
    FAILURE = "failure"
    SUCCESS = "success"
    PROMPT = "prompt"
    EVOLUTION = "evolution"
    PLANNING = "planning"
    SWARM = "swarm"
    SYSTEM = "system"
    FACT = "fact"


@dataclass(slots=True)
class MemoryRecord:
    content: str
    type: MemoryType = MemoryType.FACT
    namespace: str = "agents/"
    owner: str = "default"
    uuid: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=_utcnow)
    importance: float = 0.5
    confidence: float = 0.8
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    relationships: list[str] = field(default_factory=list)
    ttl_seconds: int | None = None
    access_count: int = 0
    last_access: datetime | None = None
    summary: str = ""
    version: int = 1
    source: str = "runtime"
    tags: list[str] = field(default_factory=list)
    origin_agent: str = ""
    workflow_id: str = ""
    execution_id: str = ""
    reasoning_id: str = ""
    cost: float = 0.0
    latency: float = 0.0
    success_score: float = 0.0
    failure_reason: str = ""
    archived: bool = False
    provider_id: str = ""

    def touch(self) -> None:
        self.access_count += 1
        self.last_access = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value if isinstance(self.type, MemoryType) else str(self.type)
        data["timestamp"] = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp
        if self.last_access is not None:
            data["last_access"] = (
                self.last_access.isoformat()
                if isinstance(self.last_access, datetime)
                else self.last_access
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        raw = dict(data)
        mem_type = raw.pop("type", MemoryType.FACT)
        if isinstance(mem_type, str):
            mem_type = MemoryType(mem_type)
        ts = raw.pop("timestamp", None)
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = _utcnow()
        last = raw.pop("last_access", None)
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        # Drop unknown keys safely
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in raw.items() if k in known}
        return cls(type=mem_type, timestamp=ts, last_access=last, **filtered)


@dataclass(slots=True)
class SearchQuery:
    text: str
    owner: str = "default"
    namespace: str | None = None
    memory_types: list[MemoryType] | None = None
    tags: list[str] | None = None
    limit: int = 5
    min_importance: float = 0.0
    min_confidence: float = 0.0
    include_archived: bool = False
    time_decay: bool = True
    workflow_id: str = ""
    execution_id: str = ""
    metadata_filters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchHit:
    record: MemoryRecord
    score: float
    signals: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ReflectionResult:
    lessons: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    successful_strategies: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PredictionResult:
    next_workflow: str = ""
    next_tool: str = ""
    next_model: str = ""
    next_planner: str = ""
    next_memory: str = ""
    next_retrieval: str = ""
    confidence: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class HealthStatus:
    healthy: bool
    provider: str
    details: dict[str, Any] = field(default_factory=dict)
