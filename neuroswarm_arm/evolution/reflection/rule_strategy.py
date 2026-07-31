"""Rule-based reflection — MVP default; proposes only."""

from __future__ import annotations

from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeView
from neuroswarm_arm.evolution.interfaces.reflection import (
    Analysis,
    PolicyDelta,
    Reflection,
    ReflectionStrategy,
)


class RuleBasedReflectionStrategy(ReflectionStrategy):
    name = "rule"

    def analyze(self, knowledge: KnowledgeView) -> Analysis:
        m = dict(knowledge.aggregate_metrics)
        findings: list[str] = []
        severity = 0.0
        accept = m.get("ascr_accept_rate", m.get("accept_rate", 0.7))
        latency = m.get("ascr_latency_ms", m.get("latency_ms", 0.0))
        kv = m.get("kv_pressure", 0.0)
        cpu = m.get("cpu_util", m.get("cpu_utilization", 0.5))
        if accept < 0.55:
            findings.append("low_accept_rate")
            severity += 0.4
        if latency > 3000:
            findings.append("high_latency")
            severity += 0.3
        if kv > 0.8:
            findings.append("high_kv_pressure")
            severity += 0.2
        if cpu > 0.85:
            findings.append("high_cpu")
            severity += 0.1
        if not findings:
            findings.append("stable")
        return Analysis(findings=tuple(findings), metrics=m, severity=min(1.0, severity))

    def reflect(self, analysis: Analysis) -> Reflection:
        hyp: list[str] = []
        if "low_accept_rate" in analysis.findings:
            hyp.append("raise_accept_or_reduce_draft")
        if "high_latency" in analysis.findings:
            hyp.append("reduce_draft_len_or_reasoning_cap")
        if "high_kv_pressure" in analysis.findings:
            hyp.append("reduce_speculation_depth")
        if "high_cpu" in analysis.findings:
            hyp.append("reduce_verify_batch")
        if not hyp:
            hyp.append("hold_or_micro_tune")
        return Reflection(
            summary=";".join(analysis.findings),
            analysis=analysis,
            hypotheses=tuple(hyp),
        )

    def propose(self, reflection: Reflection) -> list[PolicyDelta]:
        m = dict(reflection.analysis.metrics)
        params: dict[str, object] = {}
        layers: set[str] = set()
        accept = float(m.get("ascr_accept_rate", m.get("accept_rate", 0.7)))
        latency = float(m.get("ascr_latency_ms", m.get("latency_ms", 0.0)))
        draft = int(m.get("draft_len", 8))
        reasoning = int(m.get("reasoning_cap", 512))
        top_k = int(m.get("router_top_k", 3))

        if "low_accept_rate" in reflection.analysis.findings:
            params["accept_threshold"] = min(0.95, accept + 0.05 if accept < 1 else 0.85)
            params["draft_len"] = max(2, draft - 2)
            layers.update({"ascr"})
        if "high_latency" in reflection.analysis.findings:
            params["draft_len"] = max(2, int(params.get("draft_len", draft)) - 2)
            params["reasoning_cap"] = max(64, reasoning // 2)
            layers.update({"ascr", "rtg"})
        if "high_kv_pressure" in reflection.analysis.findings:
            params["speculation_depth"] = 1
            layers.add("ascr")
        if "high_cpu" in reflection.analysis.findings:
            params["verify_batch"] = 1
            params["router_top_k"] = max(1, top_k - 1)
            layers.update({"ascr", "router"})
        if not params:
            # Micro-explore: tiny draft bump when stable and accept high
            if accept > 0.8 and latency < 1500:
                params["draft_len"] = min(48, draft + 2)
                layers.add("ascr")
            else:
                return []

        return [
            PolicyDelta(
                parameters=params,
                target_layers=frozenset(layers),
                rationale=f"rule:{reflection.summary}",
                expected_reward=0.05 + 0.1 * reflection.analysis.severity,
                confidence=0.6,
                source="rule",  # always "rule" even when called via subclass.super()
            )
        ]
