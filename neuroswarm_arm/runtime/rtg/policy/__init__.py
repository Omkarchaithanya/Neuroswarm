"""Hierarchical RTG policies — L0 heuristics, L1 detectors, L2 bandit, L3 PPO."""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from typing import Any

from ..config import RTGRuntimeConfig
from ..interfaces import IPolicy
from ..models import Decision, GovernorAction, SessionState, TelemetryFrame


class HeuristicPolicy(IPolicy):
    """L0 hard constraints — evolved from legacy ReasoningGovernor."""

    policy_id = "heuristics"
    layer = "L0"

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg

    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision | None:
        rem = state.budget.remaining_tokens
        if frame.tool_confidence_top1 >= self.cfg.tool_confidence_commit and rem > 256:
            return Decision(
                action=GovernorAction.SKIP_REASONING
                if frame.thinking_tokens_so_far < 8
                else GovernorAction.EARLY_COMMIT,
                reason="tool_confidence_high",
                force_close=True,
                confidence=frame.tool_confidence_top1,
                policy_layer=self.layer,
                new_budget=min(rem, 256),
            )
        if frame.kv_pressure >= self.cfg.kv_pressure_hard:
            return Decision(
                action=GovernorAction.STOP_EARLY,
                reason="kv_pressure_hard",
                force_close=True,
                policy_layer=self.layer,
                governor_accuracy_demand=0.3,
            )
        if frame.memory_pressure >= self.cfg.memory_pressure_hard:
            return Decision(
                action=GovernorAction.DECREASE_BUDGET,
                reason="memory_pressure",
                budget_delta=-max(64, rem // 2),
                policy_layer=self.layer,
            )
        if frame.kv_pressure >= self.cfg.kv_pressure_soft and rem > 512:
            return Decision(
                action=GovernorAction.DECREASE_BUDGET,
                reason="kv_pressure_soft",
                budget_delta=-(rem - 512),
                new_budget=512,
                policy_layer=self.layer,
            )
        if frame.slo_remaining_ms < self.cfg.slo_soft_ms and rem > 256:
            soft = int(256 + 4 * frame.tool_confidence_top1 * 1024)
            return Decision(
                action=GovernorAction.DECREASE_BUDGET,
                reason="slo_soft",
                new_budget=min(rem, soft),
                budget_delta=min(0, soft - rem),
                policy_layer=self.layer,
            )
        if frame.energy_so_far_joules >= state.budget.energy_joules_budget:
            return Decision(
                action=GovernorAction.STOP_EARLY,
                reason="energy_budget",
                force_close=True,
                policy_layer=self.layer,
            )
        if rem <= 0:
            return Decision(
                action=GovernorAction.STOP_EARLY,
                reason="budget_exhausted",
                force_close=True,
                policy_layer=self.layer,
            )
        return None


class StreamingDetectorPolicy(IPolicy):
    """L1 DEER-style early exit / entropy / plateau."""

    policy_id = "streaming_detectors"
    layer = "L1"

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg

    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision | None:
        if frame.self_consistency_score >= self.cfg.self_consistency_commit:
            return Decision(
                action=GovernorAction.EARLY_COMMIT,
                reason="self_consistency",
                force_close=True,
                confidence=frame.self_consistency_score,
                policy_layer=self.layer,
                new_budget=min(state.budget.remaining_tokens, 128),
            )
        if (
            frame.token_entropy <= self.cfg.entropy_stop
            and frame.answer_stability >= 0.7
            and frame.thinking_tokens_so_far >= self.cfg.chunk_size
        ):
            return Decision(
                action=GovernorAction.EARLY_COMMIT,
                reason="entropy_stop",
                force_close=True,
                confidence=frame.model_confidence,
                policy_layer=self.layer,
            )
        if frame.plateau_score >= 0.95 and frame.thinking_tokens_so_far >= 2 * self.cfg.chunk_size:
            if frame.model_confidence < float(self.cfg.policy.get("escalation", {}).get("low_confidence", 0.45)):
                return Decision(
                    action=GovernorAction.ESCALATE_TIER,
                    reason="plateau_low_conf",
                    escalate_to_tier=min(3, frame.cascade_tier + 1),
                    policy_layer=self.layer,
                    governor_accuracy_demand=0.85,
                )
            return Decision(
                action=GovernorAction.EARLY_COMMIT,
                reason="reasoning_plateau",
                force_close=True,
                confidence=frame.confidence_ema,
                policy_layer=self.layer,
            )
        if frame.reasoning_roi < self.cfg.roi_stop and frame.thinking_tokens_so_far >= 2 * self.cfg.chunk_size:
            return Decision(
                action=GovernorAction.STOP_EARLY,
                reason="low_roi",
                force_close=True,
                policy_layer=self.layer,
            )
        # Thought-transition markers (DEER-inspired)
        chunk = (frame.chunk_text or "").lower()
        if any(tok in chunk for tok in ("wait,", "alternatively", "let me reconsider")):
            if frame.model_confidence >= 0.8:
                return Decision(
                    action=GovernorAction.EARLY_COMMIT,
                    reason="deer_transition_high_conf",
                    force_close=True,
                    confidence=frame.model_confidence,
                    policy_layer=self.layer,
                )
        return None


class SlidingWindowUCB:
    """REFRAIN-style SW-UCB over discrete confidence thresholds."""

    def __init__(self, arms: list[float], *, window: int = 50, c: float = 1.2) -> None:
        self.arms = list(arms)
        self.window = window
        self.c = c
        self._history: deque[tuple[int, float]] = deque(maxlen=window)
        self._counts: dict[int, int] = defaultdict(int)
        self._rewards: dict[int, float] = defaultdict(float)

    def select(self, rng: random.Random | None = None) -> tuple[int, float]:
        rng = rng or random.Random()
        n = max(1, len(self._history))
        best_i = 0
        best_score = -1e18
        for i, _arm in enumerate(self.arms):
            count = self._counts[i]
            if count == 0:
                return i, self.arms[i]
            mean = self._rewards[i] / count
            bonus = self.c * math.sqrt(math.log(n + 1) / count)
            score = mean + bonus
            if score > best_score:
                best_score = score
                best_i = i
        return best_i, self.arms[best_i]

    def update(self, arm_index: int, reward: float) -> None:
        if self._history and len(self._history) == self.window:
            old_i, old_r = self._history[0]
            self._counts[old_i] = max(0, self._counts[old_i] - 1)
            self._rewards[old_i] -= old_r
        self._history.append((arm_index, reward))
        self._counts[arm_index] += 1
        self._rewards[arm_index] += reward


class BanditThresholdPolicy(IPolicy):
    """L2 contextual bandit over stop thresholds."""

    policy_id = "sw_ucb"
    layer = "L2"

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg
        arms = list(cfg.thresholds.get("bandit_arms") or [0.7, 0.8, 0.85, 0.9, 0.95])
        self.bandits: dict[str, SlidingWindowUCB] = {}
        self._default_arms = [float(a) for a in arms]
        self._last_arm: dict[str, int] = {}
        self._rng = random.Random(42)

    def _key(self, frame: TelemetryFrame) -> str:
        cbin = int(frame.complexity_score * 4)
        return f"{frame.workflow_type}|{cbin}|t{frame.cascade_tier}"

    def _bandit(self, key: str) -> SlidingWindowUCB:
        if key not in self.bandits:
            self.bandits[key] = SlidingWindowUCB(
                self._default_arms, window=self.cfg.bandit_window
            )
        return self.bandits[key]

    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision | None:
        if not self.cfg.bandit_enabled:
            return None
        if frame.thinking_tokens_so_far < self.cfg.chunk_size:
            return None
        key = self._key(frame)
        bandit = self._bandit(key)
        idx, threshold = bandit.select(self._rng)
        self._last_arm[state.session_id] = idx
        conf = frame.confidence_ema or frame.model_confidence
        if conf >= threshold and frame.answer_stability >= 0.55:
            return Decision(
                action=GovernorAction.EARLY_COMMIT,
                reason=f"bandit_threshold_{threshold:.2f}",
                force_close=True,
                confidence=conf,
                policy_layer=self.layer,
                metadata={"arm": idx, "threshold": threshold, "context": key},
            )
        return None

    def feedback(self, session_id: str, frame: TelemetryFrame, tokens_used: int) -> None:
        key = self._key(frame)
        idx = self._last_arm.get(session_id)
        if idx is None:
            return
        quality = frame.model_confidence or frame.answer_stability
        norm_tokens = min(1.0, tokens_used / max(1, self.cfg.base_budget))
        reward = quality - self.cfg.bandit_beta * norm_tokens
        self._bandit(key).update(idx, reward)


class PPOPolicyScaffold(IPolicy):
    """L3 offline PPO scaffold — heuristic fallback until trained weights exist."""

    policy_id = "ppo_scaffold"
    layer = "L3"

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg
        self.weights: dict[str, float] = {
            "escalate_bias": 0.0,
            "quant_bias": 0.0,
            "skip_bias": 0.0,
        }

    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision | None:
        if not self.cfg.ppo_enabled:
            return None
        # Reward-shaped heuristic stand-in
        quality = frame.model_confidence
        cost = frame.cost_so_far_usd
        latency = 1.0 - min(1.0, frame.slo_remaining_ms / max(1.0, state.budget.latency_slo_ms))
        energy = frame.energy_so_far_joules / max(1.0, state.budget.energy_joules_budget)
        score = quality - 0.4 * cost * 100 - 0.3 * latency - 0.2 * energy
        if score < 0.2 and frame.cascade_tier < 3 and frame.complexity_score > 0.6:
            return Decision(
                action=GovernorAction.ESCALATE_TIER,
                reason="ppo_escalate",
                escalate_to_tier=frame.cascade_tier + 1,
                governor_accuracy_demand=0.9,
                policy_layer=self.layer,
            )
        if score > 0.85 and frame.tool_confidence_top1 > 0.7:
            return Decision(
                action=GovernorAction.INVOKE_TOOL,
                reason="ppo_invoke_tool",
                force_close=True,
                policy_layer=self.layer,
            )
        if frame.complexity_score < 0.25 and quality > 0.5:
            return Decision(
                action=GovernorAction.SWITCH_QUANT,
                reason="ppo_downgrade_quant",
                quant_hint="Q4_0",
                governor_accuracy_demand=0.4,
                policy_layer=self.layer,
            )
        return None

    def train_step(self, batch: list[dict[str, Any]]) -> dict[str, float]:
        # Offline stub — records batch size only
        return {"loss": 0.0, "batch": float(len(batch))}


class PolicyEngine:
    """Compose L0→L3; first non-None decision wins within priority."""

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg
        self.heuristics = HeuristicPolicy(cfg)
        self.detectors = StreamingDetectorPolicy(cfg)
        self.bandit = BanditThresholdPolicy(cfg)
        self.ppo = PPOPolicyScaffold(cfg)
        layers = cfg.policy.get("layers") or {}
        self._order: list[IPolicy] = []
        if layers.get("L0_hard_constraints", True):
            self._order.append(self.heuristics)
        if layers.get("L1_streaming_detectors", True):
            self._order.append(self.detectors)
        if layers.get("L2_bandit_thresholds", True):
            self._order.append(self.bandit)
        if layers.get("L3_ppo_scaffold", False) or cfg.ppo_enabled:
            self._order.append(self.ppo)

    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision:
        for policy in self._order:
            decision = policy.decide(frame, state)
            if decision is not None:
                return decision
        return Decision(action=GovernorAction.CONTINUE, reason="default", policy_layer="none")
