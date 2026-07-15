"""Pydantic v2 schemas for ARMORA Budget Envelope."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Hardness(str, Enum):
    SOFT = "soft"
    HARD = "hard"


class ViolationState(str, Enum):
    NONE = "none"
    WARNING = "warning"
    BREACHED = "breached"


class LifecyclePhase(str, Enum):
    CREATE = "create"
    VALIDATE = "validate"
    OPTIMIZE = "optimize"
    FREEZE = "freeze"
    EXECUTE = "execute"
    CONSUME = "consume"
    CHECK = "check"
    REPORT = "report"
    PERSIST = "persist"
    DONE = "done"
    REJECTED = "rejected"
    ABORTED = "aborted"


class FailurePolicy(str, Enum):
    ABORT = "abort"
    DEGRADE = "degrade"
    ESCALATE = "escalate"
    CONTINUE_SOFT = "continue_soft"


class CancellationPolicy(str, Enum):
    IMMEDIATE = "immediate"
    DRAIN = "drain"
    CHECKPOINT = "checkpoint"


class ExecutionSLA(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_e2e_latency_ms: float = 4000.0
    max_ttft_ms: float = 1500.0
    min_throughput_tok_s: float = 0.0
    availability_target: float = 0.99


class QualityRequirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_confidence: float = 0.0
    min_accept_rate: float = 0.0
    require_citations: bool = False
    preferred_quality_tier: str = "balanced"


class BackendPreferences(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    preferred_quantization: str = ""
    preferred_backend: str = ""
    preferred_model_tier: int = 1
    allow_speculation: bool = True
    allow_streaming: bool = True


class HardwareConstraints(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    numa_nodes: tuple[int, ...] = ()
    cpu_affinity: tuple[int, ...] = ()
    max_threads: int = 0
    require_local_kv: bool = False
    cgroup_cpu_max: str = ""
    cgroup_memory_max: str = ""


class DimensionDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, float] = Field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        return float(self.values.get(name, default))

    def merge(self, other: "DimensionDelta") -> "DimensionDelta":
        out = dict(self.values)
        for k, v in other.values.items():
            out[k] = float(out.get(k, 0.0)) + float(v)
        return DimensionDelta(values=out)

    @classmethod
    def from_mapping(cls, data: Mapping[str, float | int]) -> "DimensionDelta":
        return cls(values={str(k): float(v) for k, v in data.items()})


class ResourceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p50: DimensionDelta = Field(default_factory=DimensionDelta)
    p90: DimensionDelta = Field(default_factory=DimensionDelta)
    confidence: float = 0.7
    notes: str = ""

    @classmethod
    def single(cls, dim: str, value: float, *, confidence: float = 0.7) -> "ResourceProjection":
        d = DimensionDelta(values={dim: float(value)})
        return cls(p50=d, p90=d, confidence=confidence)

    def pick(self, percentile: str = "p90") -> DimensionDelta:
        return self.p90 if percentile == "p90" else self.p50


class AdmitDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    soft_warnings: list[str] = Field(default_factory=list)
    hard_failures: list[str] = Field(default_factory=list)
    optimized: bool = False
    degrade_actions: list[str] = Field(default_factory=list)


class AffordDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affordable: bool
    action: str
    projected: DimensionDelta = Field(default_factory=DimensionDelta)
    blocking_dims: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    message: str = ""


class PlanActionKind(str, Enum):
    FRONTIER_MODEL = "frontier_model"
    QUANT = "quant"
    TIER = "tier"
    REASONING = "reasoning"
    SPECULATE = "speculate"
    TOOL_CALL = "tool_call"
    RETRY = "retry"
    EXPAND_CONTEXT = "expand_context"
    BATCH = "batch"
    STREAM = "stream"
    CUSTOM = "custom"


class PlanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PlanActionKind
    params: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def tier(cls, n: int) -> "PlanAction":
        return cls(kind=PlanActionKind.TIER, params={"tier": int(n)})

    @classmethod
    def quant(cls, name: str) -> "PlanAction":
        return cls(kind=PlanActionKind.QUANT, params={"quantization": name})

    @classmethod
    def reasoning(cls, tokens: int) -> "PlanAction":
        return cls(kind=PlanActionKind.REASONING, params={"tokens": int(tokens)})

    @classmethod
    def speculate(cls, draft_tokens: int) -> "PlanAction":
        return cls(kind=PlanActionKind.SPECULATE, params={"draft_tokens": int(draft_tokens)})

    @classmethod
    def tool_call(cls, cost_usd: float = 0.0) -> "PlanAction":
        return cls(kind=PlanActionKind.TOOL_CALL, params={"cost_usd": float(cost_usd)})

    @classmethod
    def retry(cls) -> "PlanAction":
        return cls(kind=PlanActionKind.RETRY, params={})

    @classmethod
    def frontier_model(cls) -> "PlanAction":
        return cls(kind=PlanActionKind.FRONTIER_MODEL, params={})

    @classmethod
    def expand_context(cls, tokens: int) -> "PlanAction":
        return cls(kind=PlanActionKind.EXPAND_CONTEXT, params={"tokens": int(tokens)})

    @classmethod
    def batch(cls, size: int) -> "PlanAction":
        return cls(kind=PlanActionKind.BATCH, params={"size": int(size)})


class EnvelopeTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_role: str = "default"
    cost_usd: float | None = None
    latency_ms: float | None = None
    memory_bytes: int | None = None
    energy_joules: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    kv_bytes: int | None = None
    tool_calls: int | None = None
    cpu_seconds: float | None = None
    streaming_ms: float | None = None
    retries: int | None = None
    concurrency: int | None = None
    max_context_length: int | None = None
    max_batch_size: int | None = None
    priority: int | None = None
    min_confidence: float | None = None
    preferred_quantization: str | None = None
    preferred_backend: str | None = None
    preferred_model_tier: int | None = None
    failure_policy: FailurePolicy = FailurePolicy.DEGRADE
    cancellation_policy: CancellationPolicy = CancellationPolicy.DRAIN
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChargebackTags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = ""
    agent_id: str = ""
    workflow: str = "chat"
    model_tier: int = 1
    numa_node: int = 0
    list_cost_usd: float = 0.0
    effective_cost_usd: float = 0.0
    unallocated_share_usd: float = 0.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_envelope_id() -> UUID:
    return uuid4()


class TimestampedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("created_at", mode="before")
    @classmethod
    def _ensure_tz(cls, v: Any) -> Any:
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
