"""Heuristic cost router: map tool confidence + query signals → cascade start tier.

No PPO/RL — deterministic thresholds aligned with NSA_ROUTER_* gates.
Does not swap models; ``quant`` is a hint only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


def _f(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Reasoning / heavy markers → prefer tier3 (DeepSeek path).
_REASONING_RE = re.compile(
    r"\b(reason|think step|chain.?of.?thought|prove|derive|debug|analyze carefully|"
    r"multi-?step|plan then|deepseek)\b",
    re.I,
)


@dataclass(slots=True, frozen=True)
class CostDecision:
    tier: int
    quant: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"tier": self.tier, "quant": self.quant, "reason": self.reason}


class CostRouter:
    """Pick cascade start tier from semantic-router confidence + query hardness."""

    def __init__(
        self,
        *,
        high_conf: float | None = None,
        escalate_conf: float | None = None,
        mid_conf: float | None = None,
    ) -> None:
        # Align with Semantic MCP Router gates (0.70 high / 0.42 expand).
        self.high_conf = float(high_conf if high_conf is not None else _f("NSA_ROUTER_HIGH_CONF_GATE", 0.70))
        self.escalate_conf = float(
            escalate_conf if escalate_conf is not None else _f("NSA_ROUTER_ESCALATE_CONF", 0.42)
        )
        self.mid_conf = float(mid_conf if mid_conf is not None else _f("NSA_COST_ROUTER_MID_CONF", 0.55))

    def route(
        self,
        query: str,
        *,
        tool_confidence: float,
        plan_state: dict[str, Any] | None = None,
    ) -> CostDecision:
        conf = max(0.0, min(1.0, float(tool_confidence or 0.0)))
        text = (query or "").strip()
        words = len(text.split())
        plan_state = plan_state or {}

        forced = plan_state.get("force_tier")
        if forced is not None:
            try:
                t = max(1, min(3, int(forced)))
                return CostDecision(tier=t, quant=self._quant_for(t), reason=f"force_tier={t}")
            except (TypeError, ValueError):
                pass

        if _REASONING_RE.search(text) or words >= 80:
            return CostDecision(
                tier=3,
                quant=self._quant_for(3),
                reason="reasoning_or_long_query",
            )

        # Never start at tier1 when tool confidence is below expand gate.
        if conf < self.escalate_conf:
            return CostDecision(
                tier=3,
                quant=self._quant_for(3),
                reason=f"tool_conf={conf:.3f}<escalate={self.escalate_conf}",
            )

        if conf >= self.high_conf and words <= 24:
            return CostDecision(
                tier=1,
                quant=self._quant_for(1),
                reason=f"high_conf={conf:.3f}_short",
            )

        if conf >= self.mid_conf:
            return CostDecision(
                tier=2,
                quant=self._quant_for(2),
                reason=f"mid_conf={conf:.3f}",
            )

        # Between escalate and mid → start at 2 (ASCR can still escalate to 3).
        return CostDecision(
            tier=2,
            quant=self._quant_for(2),
            reason=f"default_mid_band conf={conf:.3f}",
        )

    @staticmethod
    def _quant_for(tier: int) -> str:
        # Hint only — tier containers already pin GGUF; do not swap weights.
        return {1: "Q4_K_M", 2: "Q5_K_M", 3: "Q5_K_M"}.get(int(tier), "Q5_K_M")
