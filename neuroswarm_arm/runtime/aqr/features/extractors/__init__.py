"""Feature engineering pipeline — RequestContext → FeatureVector."""

from __future__ import annotations

from ..models import FeatureVector, RequestContext


class FeatureExtractor:
    name: str = "base"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        raise NotImplementedError


class ReasoningScoreExtractor(FeatureExtractor):
    name = "reasoning_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        role = ctx.agent_role.lower()
        workload = ctx.workload.lower()
        score = 0.2
        if role in {"reasoning", "code"} or workload in {"reasoning", "coding"}:
            score = 0.85
        score = max(score, min(1.0, ctx.reasoning_depth))
        if ctx.governor_accuracy_demand > 0.7:
            score = min(1.0, score + 0.15)
        return {self.name: score}


class ToolLikelihoodExtractor(FeatureExtractor):
    name = "tool_likelihood"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        if ctx.agent_role.lower() in {"tool_call", "tool_calling"}:
            return {self.name: 0.9}
        if ctx.workload.lower() == "tool_calling":
            return {self.name: 0.8}
        return {self.name: 0.2}


class MemoryScoreExtractor(FeatureExtractor):
    name = "memory_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        pressure = max(ctx.memory_pressure, ctx.kv_cache_pressure)
        return {self.name: min(1.0, max(0.0, pressure))}


class CostScoreExtractor(FeatureExtractor):
    name = "cost_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        if ctx.budget_usd <= 0:
            return {self.name: 1.0}
        ratio = ctx.current_cost_usd / max(ctx.budget_usd, 1e-9)
        return {self.name: min(1.0, max(0.0, ratio))}


class QualityScoreExtractor(FeatureExtractor):
    name = "quality_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        base = 0.5
        if ctx.agent_role.lower() in {"reasoning", "code"}:
            base = 0.85
        base = max(base, ctx.governor_accuracy_demand)
        return {self.name: min(1.0, base)}


class LatencyScoreExtractor(FeatureExtractor):
    name = "latency_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        # Higher = tighter SLA pressure
        if ctx.latency_sla_ms <= 0:
            return {self.name: 0.5}
        urgency = 1.0 - min(1.0, ctx.latency_sla_ms / 8000.0)
        return {self.name: max(0.0, urgency)}


class ComputeIntensityExtractor(FeatureExtractor):
    name = "expected_compute_intensity"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        tokens = ctx.prompt_length + ctx.expected_output_tokens
        intensity = min(1.0, tokens / 2048.0)
        if ctx.reasoning_depth > 0.5:
            intensity = min(1.0, intensity + 0.2)
        return {self.name: intensity}


class CacheLocalityExtractor(FeatureExtractor):
    name = "cache_locality_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        score = 0.3
        if ctx.shared_kv_available:
            score += 0.4
        if ctx.session_id:
            score += 0.2
        score -= 0.3 * ctx.kv_cache_pressure
        return {self.name: min(1.0, max(0.0, score))}


class BackendSuitabilityExtractor(FeatureExtractor):
    name = "backend_suitability_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        healthy = sum(1 for b in ctx.backends if b.healthy)
        total = max(1, len(ctx.backends))
        load_penalty = min(1.0, ctx.worker_load)
        return {self.name: max(0.0, (healthy / total) * (1.0 - 0.5 * load_penalty))}


class QuantSuitabilityExtractor(FeatureExtractor):
    name = "quantization_suitability_score"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        # Prefer lower bits under memory pressure; higher under quality demand
        mem = max(ctx.memory_pressure, ctx.kv_cache_pressure)
        quality = ctx.governor_accuracy_demand
        score = 0.5 + 0.3 * quality - 0.3 * mem
        return {self.name: min(1.0, max(0.0, score))}


class WarmBonusExtractor(FeatureExtractor):
    name = "warm_bonus"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        if ctx.awpp_prediction and ctx.model_warm_state.get(ctx.awpp_prediction):
            return {self.name: 1.0}
        if any(ctx.model_warm_state.values()):
            return {self.name: 0.5}
        return {self.name: 0.0}


class GovernorAccuracyExtractor(FeatureExtractor):
    name = "governor_accuracy_demand"

    def extract(self, ctx: RequestContext) -> dict[str, float]:
        return {self.name: min(1.0, max(0.0, ctx.governor_accuracy_demand))}


DEFAULT_EXTRACTORS: list[FeatureExtractor] = [
    ReasoningScoreExtractor(),
    ToolLikelihoodExtractor(),
    MemoryScoreExtractor(),
    CostScoreExtractor(),
    QualityScoreExtractor(),
    LatencyScoreExtractor(),
    ComputeIntensityExtractor(),
    CacheLocalityExtractor(),
    BackendSuitabilityExtractor(),
    QuantSuitabilityExtractor(),
    WarmBonusExtractor(),
    GovernorAccuracyExtractor(),
]


class FeaturePipeline:
    def __init__(self, extractors: list[FeatureExtractor] | None = None) -> None:
        self.extractors = list(extractors or DEFAULT_EXTRACTORS)

    def run(self, ctx: RequestContext) -> FeatureVector:
        data: dict[str, float] = {}
        for ext in self.extractors:
            data.update(ext.extract(ctx))
        return FeatureVector(**{k: data.get(k, 0.0) for k in FeatureVector.model_fields})
