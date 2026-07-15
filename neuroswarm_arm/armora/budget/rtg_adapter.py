"""RTG adapter — ReasoningBudgetView over ARMORA Budget Envelope dims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neuroswarm_arm.armora.budget.tracker import BudgetTracker


@dataclass
class ReasoningBudgetView:
    """Read/write view mimicking legacy RTG BudgetEnvelope fields."""

    envelope_id: str
    tracker: BudgetTracker
    chunk_size: int = 64
    min_tokens: int = 64
    max_tokens: int = 8192

    @property
    def remaining_tokens(self) -> int:
        state = self.tracker.get_state(self.envelope_id)
        return int(state.remaining("reasoning_tokens"))

    @property
    def initial_tokens(self) -> int:
        env = self.tracker.get_envelope(self.envelope_id)
        return int(env.categories["reasoning_tokens"].limit)

    @property
    def cost_budget_usd(self) -> float:
        env = self.tracker.get_envelope(self.envelope_id)
        return float(env.categories["cost_usd"].limit)

    @property
    def cost_spent_usd(self) -> float:
        state = self.tracker.get_state(self.envelope_id)
        cat = state.categories["cost_usd"]
        return float(cat.consumed)

    @property
    def energy_joules_budget(self) -> float:
        env = self.tracker.get_envelope(self.envelope_id)
        return float(env.categories["energy_joules"].limit)

    @property
    def energy_spent_joules(self) -> float:
        state = self.tracker.get_state(self.envelope_id)
        return float(state.categories["energy_joules"].consumed)

    @property
    def latency_slo_ms(self) -> float:
        env = self.tracker.get_envelope(self.envelope_id)
        return float(env.categories["latency_ms"].limit)

    @property
    def latency_spent_ms(self) -> float:
        state = self.tracker.get_state(self.envelope_id)
        return float(state.categories["latency_ms"].consumed)

    def consume(
        self, tokens: int, *, latency_ms: float = 0.0, cost_usd: float = 0.0
    ) -> None:
        amounts: dict[str, float] = {"reasoning_tokens": float(max(0, tokens))}
        if latency_ms:
            amounts["latency_ms"] = float(latency_ms)
        if cost_usd:
            amounts["cost_usd"] = float(cost_usd)
        self.tracker.consume(self.envelope_id, amounts)

    def apply_delta(self, delta: int) -> None:
        state = self.tracker.get_state(self.envelope_id)
        cat = state.categories["reasoning_tokens"]
        new_limit = int(
            max(self.min_tokens, min(self.max_tokens, cat.remaining + delta + cat.consumed))
        )
        self.tracker.apply_limit_adjustment(self.envelope_id, {"reasoning_tokens": float(new_limit)})

    def as_legacy_dict(self) -> dict[str, Any]:
        return {
            "initial_tokens": self.initial_tokens,
            "remaining_tokens": self.remaining_tokens,
            "min_tokens": self.min_tokens,
            "max_tokens": self.max_tokens,
            "cost_budget_usd": self.cost_budget_usd,
            "cost_spent_usd": self.cost_spent_usd,
            "energy_joules_budget": self.energy_joules_budget,
            "energy_spent_joules": self.energy_spent_joules,
            "latency_slo_ms": self.latency_slo_ms,
            "latency_spent_ms": self.latency_spent_ms,
            "chunk_size": self.chunk_size,
            "envelope_id": self.envelope_id,
        }
