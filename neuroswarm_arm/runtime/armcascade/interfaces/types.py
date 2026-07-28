"""Shared ASCR datatypes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class TaskKind(str, Enum):
    FACTUAL = "factual"
    CHAT = "chat"
    REASONING = "reasoning"
    CODE = "code"
    RAG = "rag"
    TOOL_USE = "tool_use"
    PLANNING = "planning"
    MULTI_AGENT = "multi_agent"
    JSON = "json"
    STREAMING = "streaming"
    UNKNOWN = "unknown"


class AcceptanceAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    PARTIAL_ACCEPT = "partial_accept"
    REDUCE_SPECULATION = "reduce_speculation"
    INCREASE_SPECULATION = "increase_speculation"
    ESCALATE = "escalate"


class VerifyMode(str, Enum):
    SINGLE = "single"
    BLOCK = "block"
    BATCHED = "batched"
    HIERARCHICAL = "hierarchical"
    TREE = "tree"
    QUALITY = "quality"


@dataclass(slots=True)
class ASCRInitContext:
    registry: Any = None
    config: Mapping[str, Any] = field(default_factory=dict)
    metrics: Any = None
    arm: Any = None


@dataclass(slots=True)
class Classification:
    task_kind: TaskKind = TaskKind.UNKNOWN
    complexity: float = 0.5
    entropy_estimate: float = 0.5
    expected_reasoning_depth: float = 0.0
    expected_latency_ms: float = 500.0
    expected_acceptance: float = 0.7
    recommended_strategy: str = "draft_model"
    recommended_verify: str = "block"
    recommended_graph: str = "default_linear"
    recommended_start_tier: int = 1
    hardness_band: str = "basic"
    signals: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ProposalToken:
    text: str
    token_id: int | None = None
    logprob: float | None = None
    rank: int = 0


@dataclass(slots=True)
class Proposal:
    tokens: list[ProposalToken] = field(default_factory=list)
    text: str = ""
    strategy: str = ""
    draft_len: int = 0
    confidence: float = 0.0
    source_tier: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        strategy: str,
        source_tier: int = 1,
        confidence: float = 0.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> Proposal:
        words = text.split() if text.strip() else []
        tokens = [ProposalToken(text=w) for w in words]
        return cls(
            tokens=tokens,
            text=text,
            strategy=strategy,
            draft_len=len(tokens),
            confidence=confidence,
            source_tier=source_tier,
            metadata=dict(metadata or {}),
        )


@dataclass(slots=True)
class ProposalRequest:
    prompt_text: str
    messages: list[dict[str, str]]
    draft_len: int
    max_tokens: int
    temperature: float = 0.2
    session_id: str = ""
    quant: str = ""
    kv_handle: str | None = None
    classification: Classification | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerifyRequest:
    messages: list[dict[str, str]]
    prompt_text: str
    mode: VerifyMode = VerifyMode.BLOCK
    accept_threshold: float = 0.5
    max_tokens: int = 1024
    temperature: float = 0.2
    session_id: str = ""
    quant: str = ""
    kv_handle: str | None = None
    verifier_tier: int = 2
    batch_size: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerifyResult:
    accepted_prefix_len: int = 0
    rejected: bool = False
    agreement: float = 0.0
    entropy: float = 0.5
    text: str = ""
    mode: VerifyMode = VerifyMode.BLOCK
    logits_available: bool = False
    quality_score: float = 0.0
    latency_ms: float = 0.0
    backend: str = ""
    model: str = ""
    tier_used: int = 2
    metrics: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AcceptanceSignals:
    confidence: float
    agreement: float
    entropy: float
    quality_score: float
    historical_acceptance: float
    task_kind: TaskKind
    tool_confidence: float
    reasoning_confidence: float
    latency_budget_ms: float
    latency_used_ms: float
    cpu_utilization: float
    kv_pressure: float
    cache_hit_ratio: float
    draft_len: int
    accepted_prefix_len: int
    accept_threshold: float
    escalate_threshold: float
    is_terminal_tier: bool = False


@dataclass(slots=True)
class AcceptanceDecision:
    action: AcceptanceAction
    accepted_prefix_len: int = 0
    reason: str = ""
    adjust_draft_delta: int = 0


@dataclass(slots=True)
class ThresholdSet:
    draft_len: int = 8
    accept_threshold: float = 0.7
    verify_batch_size: int = 1
    escalate_threshold: float = 0.4
    speculation_depth: int = 1
    max_rounds: int = 4
    # Quality-cascade path (separate from speculative logits accept_threshold).
    quality_accept_threshold: float = 0.55
    quality_early_accept_floor: float = 0.52


@dataclass(slots=True)
class ThresholdInputs:
    latency_budget_ms: float = 4000.0
    latency_used_ms: float = 0.0
    cpu_utilization: float = 0.5
    numa_locality: float = 1.0
    kv_pressure: float = 0.0
    governor_cap: float = 1.0
    historical_acceptance: float = 0.7
    complexity: float = 0.5
    entropy_estimate: float = 0.5
    base_draft_len: int = 8
    base_accept_threshold: float = 0.7
    base_escalate_threshold: float = 0.4
    base_verify_batch: int = 1
    base_depth: int = 1
    base_max_rounds: int = 4


@dataclass(slots=True)
class EscalationNode:
    id: str
    kind: str = "tier"  # tier | tool | memory | accept | terminal
    tier_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EscalationEdge:
    source: str
    target: str
    condition: str = "always"  # always | low_confidence | tool_needed | memory_needed
    weight: float = 1.0


@dataclass(slots=True)
class EscalationGraph:
    name: str
    nodes: dict[str, EscalationNode] = field(default_factory=dict)
    edges: list[EscalationEdge] = field(default_factory=list)
    start: str = "tier1"


@dataclass(slots=True)
class EscalationState:
    current: str
    confidence: float = 0.0
    tool_needed: bool = False
    memory_needed: bool = False
    visited: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PolicyDecision:
    proposal_strategy: str = "draft_model"
    verify_strategy: str = "block"
    graph_name: str = "default_linear"
    draft_backend: str = "tier1"
    verify_backend: str = "tier2"
    escalate_backend: str = "tier3"
    thresholds: ThresholdSet = field(default_factory=ThresholdSet)
    quality_cascade_fallback: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ASCRRuntimeState:
    committed_text: str = ""
    rounds: int = 0
    accepted_tokens: int = 0
    rejected_tokens: int = 0
    draft_tokens: int = 0
    verifier_calls: int = 0
    escalations: int = 0
    mode: str = "speculative"  # speculative | quality_cascade
    historical_acceptance: float = 0.7
    last_confidence: float = 0.0
    acr_context_delta: str = ""  # optional ACR compact context from memory escalate


def approx_tokens(text: str) -> int:
    if not text.strip():
        return 0
    return max(1, len(text.split()))


def build_messages(
    messages: Sequence[Mapping[str, str]],
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    out = [dict(m) for m in messages]
    if system_prompt:
        out = [{"role": "system", "content": system_prompt}] + out
    return out
