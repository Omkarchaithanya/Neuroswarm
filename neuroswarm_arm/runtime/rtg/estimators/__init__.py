"""RTG estimators — budget prediction, ROI, answer stability."""

from __future__ import annotations

from ..config import RTGRuntimeConfig
from ..interfaces import IEstimator
from ..models import BudgetEnvelope, SessionState, TelemetryFrame


class BudgetPredictor(IEstimator):
    """TALE-style complexity → initial token budget."""

    name = "budget_predictor"

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg

    def estimate(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        # Side-effect free; prediction applied by allocator.
        return frame

    def predict_tokens(self, frame: TelemetryFrame) -> int:
        base = float(self.cfg.base_budget)
        complexity = float(frame.complexity_score or 0.5)
        alpha = float(self.cfg.policy.get("cost_alpha_tool", 0.75)) if self.cfg.policy else 0.75
        # budgets.yaml may store cost_alpha_tool — also check thresholds/budgets via attrs
        tool_c = float(frame.tool_confidence_top1 or 0.0)
        raw = base * max(0.15, complexity) * (1.0 - alpha * tool_c)
        # Token elasticity floor: never go below min after soft clamp
        return int(max(self.cfg.min_budget, min(self.cfg.max_budget, round(raw))))


class ReasoningROIEstimator(IEstimator):
    name = "reasoning_roi"

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg

    def estimate(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        conf = frame.confidence_ema or frame.model_confidence
        prev = state.confidence_history[-2] if len(state.confidence_history) >= 2 else conf
        delta_acc = max(0.0, conf - prev)
        tokens = max(1, frame.thinking_tokens_so_far - (state.budget.initial_tokens - state.budget.remaining_tokens - 1))
        # Use last chunk as denominator proxy
        chunk = max(1, self.cfg.chunk_size)
        cost = (chunk / 1000.0) * self.cfg.cost_per_1k_tokens
        latency = max(1.0, state.budget.latency_spent_ms / max(1, len(state.confidence_history)))
        denom = cost + (latency / 1000.0) * 0.001
        frame.expected_accuracy_gain = delta_acc
        frame.reasoning_roi = delta_acc / max(denom, 1e-9)
        return frame


class AnswerStabilityEstimator(IEstimator):
    name = "answer_stability"

    def estimate(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        text = frame.accumulated_text.strip()
        if not text:
            frame.answer_stability = 0.0
            return frame
        # Prefer final-answer like markers
        markers = ("final answer", "answer:", "therefore", "tool_call", "```")
        lowered = text.lower()
        has_marker = any(m in lowered for m in markers)
        # Stability from self-consistency + low entropy
        frame.answer_stability = max(
            0.0,
            min(
                1.0,
                0.5 * frame.self_consistency_score
                + 0.3 * (1.0 - frame.token_entropy)
                + (0.2 if has_marker else 0.0),
            ),
        )
        return frame


def build_envelope(cfg: RTGRuntimeConfig, tokens: int, frame: TelemetryFrame) -> BudgetEnvelope:
    return BudgetEnvelope(
        initial_tokens=tokens,
        remaining_tokens=tokens,
        min_tokens=cfg.min_budget,
        max_tokens=cfg.max_budget,
        cost_budget_usd=0.05,
        energy_joules_budget=cfg.energy_joules_budget,
        latency_slo_ms=frame.slo_remaining_ms or cfg.slo_soft_ms,
        chunk_size=cfg.chunk_size,
    )
