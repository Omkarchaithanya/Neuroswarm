"""RTG typed models — telemetry, budgets, decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GovernorAction(str, Enum):
    CONTINUE = "CONTINUE"
    PAUSE = "PAUSE"
    STOP_EARLY = "STOP_EARLY"
    INCREASE_BUDGET = "INCREASE_BUDGET"
    DECREASE_BUDGET = "DECREASE_BUDGET"
    ESCALATE_TIER = "ESCALATE_TIER"
    DOWNGRADE_TIER = "DOWNGRADE_TIER"
    INVOKE_TOOL = "INVOKE_TOOL"
    SKIP_REASONING = "SKIP_REASONING"
    EARLY_COMMIT = "EARLY_COMMIT"
    SWITCH_QUANT = "SWITCH_QUANT"
    SWITCH_BACKEND = "SWITCH_BACKEND"


class SessionPhase(str, Enum):
    ADMIT = "ADMIT"
    ALLOCATE = "ALLOCATE"
    STREAMING = "STREAMING"
    FINALIZE = "FINALIZE"
    DONE = "DONE"


@dataclass(slots=True)
class BudgetEnvelope:
    """Legacy RTG per-request envelope.

    Deprecated: prefer ARMORA ``neuroswarm_arm.armora.budget.BudgetEnvelope``
    and ``ReasoningBudgetView``. This dataclass remains for RTG internal compat.
    """

    initial_tokens: int = 4096
    remaining_tokens: int = 4096
    min_tokens: int = 64
    max_tokens: int = 8192
    cost_budget_usd: float = 0.05
    cost_spent_usd: float = 0.0
    energy_joules_budget: float = 50.0
    energy_spent_joules: float = 0.0
    latency_slo_ms: float = 4000.0
    latency_spent_ms: float = 0.0
    chunk_size: int = 64
    armora_envelope_id: str = ""

    def consume(self, tokens: int, *, latency_ms: float = 0.0, cost_usd: float = 0.0) -> None:
        self.remaining_tokens = max(0, self.remaining_tokens - max(0, tokens))
        self.latency_spent_ms += max(0.0, latency_ms)
        self.cost_spent_usd += max(0.0, cost_usd)

    def apply_delta(self, delta: int) -> None:
        self.remaining_tokens = int(
            max(self.min_tokens, min(self.max_tokens, self.remaining_tokens + delta))
        )
        self.initial_tokens = max(self.initial_tokens, self.remaining_tokens + 0)

    @classmethod
    def from_armora_view(cls, view: Any) -> "BudgetEnvelope":
        """Build legacy RTG envelope from ARMORA ReasoningBudgetView."""
        return cls(
            initial_tokens=int(view.initial_tokens),
            remaining_tokens=int(view.remaining_tokens),
            min_tokens=int(view.min_tokens),
            max_tokens=int(view.max_tokens),
            cost_budget_usd=float(view.cost_budget_usd),
            cost_spent_usd=float(view.cost_spent_usd),
            energy_joules_budget=float(view.energy_joules_budget),
            energy_spent_joules=float(view.energy_spent_joules),
            latency_slo_ms=float(view.latency_slo_ms),
            latency_spent_ms=float(view.latency_spent_ms),
            chunk_size=int(getattr(view, "chunk_size", 64)),
            armora_envelope_id=str(getattr(view, "envelope_id", "")),
        )


@dataclass(slots=True)
class TelemetryFrame:
    """Unified observation snapshot for one control tick."""

    session_id: str = ""
    agent_id: str = ""
    agent_role: str = ""
    workflow_type: str = "chat"
    agent_priority: float = 0.5
    prompt_text: str = ""
    prompt_tokens: int = 0
    thinking_tokens_so_far: int = 0
    completion_tokens_so_far: int = 0
    chunk_text: str = ""
    accumulated_text: str = ""

    # Semantic / tool
    tool_confidence_top1: float = 0.0
    tool_confidence_topk_mean: float = 0.0
    tool_names: list[str] = field(default_factory=list)
    semantic_entropy: float = 1.0

    # Confidence / uncertainty
    model_confidence: float = 0.0
    self_consistency_score: float = 0.0
    answer_stability: float = 0.0
    token_entropy: float = 1.0
    confidence_ema: float = 0.0
    plateau_score: float = 0.0
    complexity_score: float = 0.5
    expected_accuracy_gain: float = 0.1
    reasoning_roi: float = 1.0

    # Memory / KV
    kv_pressure: float = 0.0
    kv_hit_rate: float = 0.0
    kv_storage_tier: int = 1
    kv_migration_latency_ms: float = 0.0
    kv_dedup_ratio: float = 0.0
    memory_pressure: float = 0.0

    # SLO / cost
    slo_remaining_ms: float = 4000.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    cost_so_far_usd: float = 0.0
    energy_so_far_joules: float = 0.0

    # Cascade / backend
    cascade_tier: int = 1
    quantization: str = ""
    backend: str = ""
    throughput_tok_s: float = 0.0

    # Hardware
    cpu_utilization: float = 0.0
    memory_bandwidth_gbs: float = 0.0
    l3_miss_rate: float = 0.0
    numa_node: int = 0
    pmu_cycles: float = 0.0
    pmu_instructions: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_plan_state(cls, plan: Any, **overrides: Any) -> TelemetryFrame:
        """Build frame from legacy PlanState-compatible object."""
        base = {
            "tool_confidence_top1": float(getattr(plan, "tool_confidence_top1", 0.0) or 0.0),
            "kv_pressure": float(getattr(plan, "kv_pressure", 0.0) or 0.0),
            "kv_hit_rate": float(getattr(plan, "kv_hit_rate", 0.0) or 0.0),
            "kv_storage_tier": int(getattr(plan, "kv_storage_tier", 1) or 1),
            "kv_migration_latency_ms": float(
                getattr(plan, "kv_migration_latency_ms", 0.0) or 0.0
            ),
            "memory_pressure": float(getattr(plan, "memory_pressure", 0.0) or 0.0),
            "slo_remaining_ms": float(getattr(plan, "slo_remaining_ms", 4000.0) or 4000.0),
            "self_consistency_score": float(
                getattr(plan, "self_consistency_score", 0.0) or 0.0
            ),
            "cascade_tier": int(getattr(plan, "cascade_tier_used", 1) or 1),
            "cost_so_far_usd": float(getattr(plan, "cost_so_far_usd", 0.0) or 0.0),
            "session_id": str(getattr(plan, "session_id", "") or ""),
        }
        base.update(overrides)
        return cls(**base)


@dataclass(slots=True)
class Decision:
    action: GovernorAction = GovernorAction.CONTINUE
    reason: str = ""
    budget_delta: int = 0
    new_budget: int | None = None
    escalate_to_tier: int | None = None
    quant_hint: str | None = None
    governor_accuracy_demand: float = 0.0
    force_close: bool = False
    confidence: float = 0.0
    policy_layer: str = "L1"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.action in {
            GovernorAction.STOP_EARLY,
            GovernorAction.EARLY_COMMIT,
            GovernorAction.INVOKE_TOOL,
            GovernorAction.SKIP_REASONING,
        }


@dataclass(slots=True)
class SessionState:
    session_id: str
    phase: SessionPhase = SessionPhase.ADMIT
    budget: BudgetEnvelope = field(default_factory=BudgetEnvelope)
    frame: TelemetryFrame = field(default_factory=TelemetryFrame)
    decisions: list[Decision] = field(default_factory=list)
    confidence_history: list[float] = field(default_factory=list)
    entropy_history: list[float] = field(default_factory=list)
    text_history: list[str] = field(default_factory=list)
    started_ms: float = 0.0
    last_action: GovernorAction = GovernorAction.CONTINUE
