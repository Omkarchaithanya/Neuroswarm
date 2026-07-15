"""Resilience policy engine — no hardcoded routing."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import Field

from .exceptions import PolicyError
from .execution import ExecutionSnapshot
from .fallback import default_dimension_configs
from .models import (
    CascadeStrategy,
    FallbackDimensionConfig,
    RuntimeSignals,
    ScoreWeights,
    _Frozen,
)


class ResiliencePolicy(_Frozen):
    """Declarative resilience policy — preferred models + constraints."""

    policy_id: str
    name: str = ""
    preferred_models: list[str] = Field(default_factory=list)
    fallback_chains: dict[str, list[str]] = Field(default_factory=dict)
    backend_preferences: list[str] = Field(default_factory=list)
    quantization_preferences: list[str] = Field(default_factory=list)
    context_preferences: list[str] = Field(default_factory=list)
    thread_preferences: list[str] = Field(default_factory=list)
    reasoning_preferences: list[str] = Field(default_factory=list)
    cascade_strategy: CascadeStrategy = CascadeStrategy.SEQUENTIAL
    dimensions: list[FallbackDimensionConfig] = Field(
        default_factory=default_dimension_configs
    )
    max_budget_usd: float | None = None
    max_latency_ms: float = 4000.0
    min_context_length: int = 0
    max_memory_gb: float = 16.0
    failure_threshold: int = 2
    min_health_score: float = 0.55
    allow_tool_disable: bool = True
    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)
    priority: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEngine:
    """Match policies for an active plan + signals (deterministic)."""

    def __init__(
        self,
        policies: list[ResiliencePolicy] | None = None,
        *,
        external: Any = None,
    ) -> None:
        self._policies = list(policies or [])
        self._external = external

    @property
    def policies(self) -> list[ResiliencePolicy]:
        return list(self._policies)

    def register(self, policy: ResiliencePolicy) -> None:
        if not policy.policy_id:
            raise PolicyError("policy_id required")
        self._policies = [p for p in self._policies if p.policy_id != policy.policy_id]
        self._policies.append(policy)
        self._policies.sort(key=lambda p: (-p.priority, p.policy_id))

    def get(self, policy_id: str) -> ResiliencePolicy | None:
        for p in self._policies:
            if p.policy_id == policy_id:
                return p
        return None

    def match(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ResiliencePolicy | None:
        """Return highest-priority matching policy, or default if registered."""
        ctx = dict(context or {})
        ctx.setdefault("model", plan.model)
        ctx.setdefault("backend", plan.backend)
        ctx.setdefault("execution_id", plan.execution_id)

        matched: list[ResiliencePolicy] = []
        for policy in self._policies:
            if self._matches(policy, plan, signals, ctx):
                matched.append(policy)
        if not matched:
            return None
        matched.sort(key=lambda p: (-p.priority, p.policy_id))
        return matched[0]

    def chain_for(self, policy: ResiliencePolicy, model_id: str) -> list[str]:
        """Fallback chain starting after *model_id* (or full preferred list)."""
        chain = list(policy.fallback_chains.get(model_id, []))
        if chain:
            return chain
        prefs = list(policy.preferred_models)
        if model_id in prefs:
            idx = prefs.index(model_id)
            return prefs[idx + 1 :]
        return [m for m in prefs if m != model_id]

    def _matches(
        self,
        policy: ResiliencePolicy,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        context: Mapping[str, Any],
    ) -> bool:
        if self._external is not None:
            pred = f"resilience.policy.{policy.policy_id}"
            try:
                if not self._external.evaluate_predicate(pred, dict(context)):
                    return False
            except Exception as exc:  # pragma: no cover - port failures
                raise PolicyError(f"external policy predicate failed: {exc}") from exc

        # Match if preferred models empty (catch-all) or current model in chain keys / preferred
        if policy.preferred_models or policy.fallback_chains:
            known = set(policy.preferred_models) | set(policy.fallback_chains.keys())
            for chain in policy.fallback_chains.values():
                known.update(chain)
            if plan.model not in known and plan.model not in policy.preferred_models:
                # Still match catch-all when failures exceed threshold
                if signals.historical_failures < policy.failure_threshold:
                    return False
        return True


def default_policy() -> ResiliencePolicy:
    """Production-safe default cascade chain."""
    return ResiliencePolicy(
        policy_id="default",
        name="default-model-cascade",
        preferred_models=[
            "Qwen3-8B",
            "Qwen3-3B",
            "Phi-4-Mini",
            "Gemma",
            "TinyLlama",
        ],
        fallback_chains={
            "Qwen3-8B": ["Qwen3-3B", "Phi-4-Mini", "Gemma", "TinyLlama"],
            "Qwen3-3B": ["Phi-4-Mini", "Gemma", "TinyLlama"],
            "Phi-4-Mini": ["Gemma", "TinyLlama"],
            "Gemma": ["TinyLlama"],
        },
        backend_preferences=["llama_cpp", "sglang", "vllm"],
        quantization_preferences=["Q5_K_M", "Q4_K_M", "Q3_K_M"],
        failure_threshold=1,
        priority=0.0,
    )
