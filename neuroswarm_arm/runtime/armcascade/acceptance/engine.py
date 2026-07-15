"""Adaptive acceptance decisions."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import (
    AcceptanceEngine,
    ConfidenceEngine,
)
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    AcceptanceAction,
    AcceptanceDecision,
    AcceptanceSignals,
)
from neuroswarm_arm.runtime.armcascade.confidence.engine import FusedConfidenceEngine


class AdaptiveAcceptanceEngine(AcceptanceEngine):
    def __init__(self, confidence: ConfidenceEngine | None = None) -> None:
        self.confidence = confidence or FusedConfidenceEngine()

    def decide(self, signals: AcceptanceSignals) -> AcceptanceDecision:
        fused = self.confidence.fuse(signals)
        # Dataclass is mutable; publish fused score for callers.
        object.__setattr__(signals, "confidence", fused)

        if signals.is_terminal_tier:
            return AcceptanceDecision(
                action=AcceptanceAction.ACCEPT,
                accepted_prefix_len=max(
                    signals.accepted_prefix_len, signals.draft_len
                ),
                reason="terminal_tier",
            )

        # Latency pressure → reduce speculation or escalate early.
        budget = max(signals.latency_budget_ms, 1.0)
        pressure = signals.latency_used_ms / budget
        if pressure > 0.9 and fused < signals.accept_threshold:
            return AcceptanceDecision(
                action=AcceptanceAction.ESCALATE,
                reason="latency_pressure",
            )

        if fused >= signals.accept_threshold and signals.accepted_prefix_len > 0:
            return AcceptanceDecision(
                action=AcceptanceAction.ACCEPT,
                accepted_prefix_len=signals.accepted_prefix_len,
                reason="fused_accept",
            )

        if (
            signals.accepted_prefix_len > 0
            and signals.accepted_prefix_len < signals.draft_len
            and fused >= signals.escalate_threshold
        ):
            return AcceptanceDecision(
                action=AcceptanceAction.PARTIAL_ACCEPT,
                accepted_prefix_len=signals.accepted_prefix_len,
                reason="prefix_match",
            )

        if fused < signals.escalate_threshold:
            return AcceptanceDecision(
                action=AcceptanceAction.ESCALATE,
                reason="below_escalate_threshold",
            )

        if signals.historical_acceptance > 0.8 and signals.entropy < 0.4:
            return AcceptanceDecision(
                action=AcceptanceAction.INCREASE_SPECULATION,
                accepted_prefix_len=signals.accepted_prefix_len,
                adjust_draft_delta=2,
                reason="high_history_low_entropy",
            )

        if signals.kv_pressure > 0.85 or signals.cpu_utilization > 0.9:
            return AcceptanceDecision(
                action=AcceptanceAction.REDUCE_SPECULATION,
                accepted_prefix_len=signals.accepted_prefix_len,
                adjust_draft_delta=-2,
                reason="resource_pressure",
            )

        if signals.accepted_prefix_len == 0:
            return AcceptanceDecision(
                action=AcceptanceAction.REJECT,
                reason="zero_prefix",
            )

        return AcceptanceDecision(
            action=AcceptanceAction.PARTIAL_ACCEPT,
            accepted_prefix_len=signals.accepted_prefix_len,
            reason="default_partial",
        )
