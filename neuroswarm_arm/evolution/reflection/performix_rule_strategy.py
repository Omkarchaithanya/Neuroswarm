"""Performix-aware rule reflection — knobs only when honest apx metrics exist."""

from __future__ import annotations

from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeView
from neuroswarm_arm.evolution.interfaces.reflection import (
    Analysis,
    PolicyDelta,
    Reflection,
)
from neuroswarm_arm.evolution.optimization.knobs import clamp_parameters
from neuroswarm_arm.evolution.reflection.rule_strategy import RuleBasedReflectionStrategy


def _has_performix_signal(m: dict) -> bool:
    """True only when Performix is available and at least one real key is present."""
    avail = float(m.get("performix_available", 0.0) or 0.0)
    if avail <= 0.0:
        return False
    # Require an honest key to be present (membership), not a silent 0 default.
    return "ipc" in m or "hotspot_top_pct" in m or "cache_miss_rate" in m


class PerformixAwareRuleStrategy(RuleBasedReflectionStrategy):
    """RuleBased + Performix signals. Never invents IPC / hotspot counters."""

    name = "performix_rule"

    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        base = super().analyze(knowledge)
        m = dict(base.metrics)
        if not _has_performix_signal(m):
            return base

        findings = list(base.findings)
        severity = float(base.severity)

        if "ipc" in m:
            ipc = float(m["ipc"])
            if ipc < 1.0:
                findings.append("performix_low_ipc")
                severity += 0.25
            elif ipc > 1.5:
                findings.append("performix_healthy_ipc")

        if "cache_miss_rate" in m and float(m["cache_miss_rate"]) > 0.1:
            findings.append("performix_high_cache_miss")
            severity += 0.2

        if "hotspot_top_pct" in m and float(m["hotspot_top_pct"]) > 50.0:
            findings.append("performix_hot_decode")
            severity += 0.15

        # Drop generic "stable" if we have Performix-specific findings
        if any(f.startswith("performix_") for f in findings) and "stable" in findings:
            findings = [f for f in findings if f != "stable"]

        return Analysis(
            findings=tuple(dict.fromkeys(findings)),
            metrics=m,
            severity=min(1.0, severity),
        )

    def reflect(self, analysis: Analysis) -> Reflection:
        base = super().reflect(analysis)
        hyp = list(base.hypotheses)
        if "performix_low_ipc" in analysis.findings or "performix_high_cache_miss" in analysis.findings:
            hyp.append("reduce_draft_raise_escalate")
        if "performix_hot_decode" in analysis.findings:
            hyp.append("prefer_cheaper_quant_lower_reasoning")
        if "performix_healthy_ipc" in analysis.findings:
            hyp.append("micro_explore_draft")
        return Reflection(
            summary=";".join(analysis.findings),
            analysis=analysis,
            hypotheses=tuple(dict.fromkeys(hyp)),
        )

    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        m = dict(reflection.analysis.metrics)
        if not _has_performix_signal(m):
            return super().propose(reflection)

        params: dict[str, object] = {}
        layers: set[str] = set()
        draft = int(m.get("draft_len", 8))
        escalate = float(m.get("escalate_threshold", m.get("ascr_escalate_threshold", 0.4)))
        reasoning = int(m.get("reasoning_cap", 512))
        accept = float(m.get("ascr_accept_rate", m.get("accept_rate", 0.7)))

        findings = reflection.analysis.findings
        if "performix_low_ipc" in findings or "performix_high_cache_miss" in findings:
            params["draft_len"] = max(2, draft - 2)
            params["escalate_threshold"] = min(0.95, escalate + 0.05)
            layers.add("ascr")
        if "performix_hot_decode" in findings:
            params["quant_preference"] = "Q4_0"
            params["reasoning_cap"] = max(64, reasoning // 2)
            layers.update({"aqr", "rtg"})
        if "performix_healthy_ipc" in findings and accept > 0.8:
            # Only bump if we did not already shrink draft this cycle
            if "draft_len" not in params:
                params["draft_len"] = min(48, draft + 2)
                layers.add("ascr")

        if not params:
            # Fall back to base rule proposals (accept/latency etc.)
            return [
                PolicyDelta(
                    parameters=d.parameters,
                    target_layers=d.target_layers,
                    rationale=f"performix_fallback:{d.rationale}",
                    expected_reward=d.expected_reward,
                    confidence=d.confidence,
                    source=self.name,
                )
                for d in super().propose(reflection)
            ]

        clamped = clamp_parameters(params)
        return [
            PolicyDelta(
                parameters=clamped,
                target_layers=frozenset(layers),
                rationale=(
                    f"performix_rule:{reflection.summary}"
                    f"|ipc={m.get('ipc')}|hot={m.get('hotspot_top_pct')}"
                    f"|cmr={m.get('cache_miss_rate')}"
                ),
                expected_reward=0.08 + 0.1 * reflection.analysis.severity,
                confidence=0.65,
                source=self.name,
            )
        ]
