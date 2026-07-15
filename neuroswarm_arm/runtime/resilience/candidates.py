"""Fallback candidate generation across enabled dimensions."""

from __future__ import annotations

from . import backend as backend_dim
from . import context as context_dim
from . import events as ev
from . import quantization as quant_dim
from . import reasoning as reasoning_dim
from . import threads as threads_dim
from ._utils import new_id
from .execution import ExecutionSnapshot
from .fallback import config_for, enabled_dimensions, resolve_cascade_strategy
from .models import (
    CascadeStrategy,
    FallbackCandidate,
    FallbackDimension,
    ModelProfile,
    RuntimeSignals,
)
from .policy import ResiliencePolicy


class CandidateGenerator:
    """Generate deterministic fallback candidates from policy + catalog."""

    def __init__(self, *, events: ev.EventBus | None = None) -> None:
        self._events = events

    def generate(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
    ) -> list[FallbackCandidate]:
        dims = enabled_dimensions(list(policy.dimensions))
        strategy = resolve_cascade_strategy(policy.cascade_strategy)
        chain = self._model_chain(plan, policy, catalog)

        candidates: list[FallbackCandidate] = []
        for model_id in chain:
            profile = catalog.get(model_id)
            if profile is None:
                continue
            base = self._base_candidate(plan, profile, signals, policy, dims)
            expanded = self._expand_dimensions(
                base, plan, profile, signals, policy, dims, strategy
            )
            candidates.extend(expanded)

        # Deduplicate by (model, backend, quant, context, threads, reasoning, tools)
        unique: dict[tuple, FallbackCandidate] = {}
        for c in candidates:
            key = (
                c.model_id,
                c.backend,
                c.quant,
                c.context_length,
                c.thread_count,
                c.reasoning_budget,
                c.tools_enabled,
                c.cascade_strategy,
            )
            if key not in unique:
                unique[key] = c
        out = list(unique.values())

        if self._events is not None:
            self._events.emit(
                ev.CandidateGenerated(
                    execution_id=plan.execution_id,
                    policy_id=policy.policy_id,
                    model_id=plan.model,
                    count=len(out),
                )
            )
        return out

    def _model_chain(
        self,
        plan: ExecutionSnapshot,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
    ) -> list[str]:
        dims = enabled_dimensions(list(policy.dimensions))
        if FallbackDimension.MODEL_TIER not in dims:
            return [plan.model] if plan.model in catalog else list(catalog.keys())[:1]

        chain = list(policy.fallback_chains.get(plan.model, []))
        if not chain:
            prefs = list(policy.preferred_models)
            if plan.model in prefs:
                chain = prefs[prefs.index(plan.model) + 1 :]
            else:
                chain = [m for m in prefs if m != plan.model]
        # Always consider current model first for non-model dimension fallbacks
        ordered = [plan.model] + [m for m in chain if m != plan.model]
        return [m for m in ordered if m in catalog]

    def _base_candidate(
        self,
        plan: ExecutionSnapshot,
        profile: ModelProfile,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        dims: list[FallbackDimension],
    ) -> FallbackCandidate:
        quality_delta = 0.0
        if profile.model_id != plan.model:
            # Tier / parameter heuristic
            quality_delta = min(0.0, (profile.parameter_count - _param(plan, profile)) / 10.0)
            if profile.priority < 1.0:
                quality_delta -= (1.0 - profile.priority) * 0.1

        changed: list[FallbackDimension] = []
        if profile.model_id != plan.model and FallbackDimension.MODEL_TIER in dims:
            changed.append(FallbackDimension.MODEL_TIER)

        backends = backend_dim.compatible_backends(profile, policy.backend_preferences)
        backend = backends[0] if backends else plan.backend
        quants = quant_dim.compatible_quants(profile, policy.quantization_preferences)
        quant = quants[0] if quants else plan.quant

        return FallbackCandidate(
            candidate_id=new_id("cand_"),
            model_id=profile.model_id,
            backend=backend if backend == plan.backend else backend,
            quant=quant if profile.model_id == plan.model else quant,
            context_length=min(profile.context_length, plan.context_length),
            thread_count=plan.thread_count,
            reasoning_budget=plan.reasoning_budget,
            tools_enabled=plan.tools_enabled,
            cascade_strategy=policy.cascade_strategy,
            dimensions_changed=changed,
            quality_delta=quality_delta,
            latency_delta=profile.estimated_latency - _latency_hint(plan, profile),
            cost_delta=profile.estimated_cost - 0.001,
            memory_delta=profile.estimated_memory - 4.0,
            reason="model_fallback" if profile.model_id != plan.model else "same_model",
        )

    def _expand_dimensions(
        self,
        base: FallbackCandidate,
        plan: ExecutionSnapshot,
        profile: ModelProfile,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        dims: list[FallbackDimension],
        strategy: CascadeStrategy,
    ) -> list[FallbackCandidate]:
        pool: list[FallbackCandidate] = [base]

        if FallbackDimension.BACKEND in dims:
            cfg = config_for(list(policy.dimensions), FallbackDimension.BACKEND)
            prefs = list(cfg.preferences) if cfg and cfg.preferences else policy.backend_preferences
            backends = backend_dim.compatible_backends(profile, prefs)
            max_steps = cfg.max_steps if cfg else 4
            extras: list[FallbackCandidate] = []
            for b in backends[:max_steps]:
                if b == base.backend:
                    continue
                extras.append(backend_dim.with_backend(base, b))
            if strategy == CascadeStrategy.SEQUENTIAL:
                pool.extend(extras[:1])
            else:
                pool.extend(extras)

        if FallbackDimension.QUANTIZATION in dims:
            cfg = config_for(list(policy.dimensions), FallbackDimension.QUANTIZATION)
            prefs = (
                list(cfg.preferences)
                if cfg and cfg.preferences
                else policy.quantization_preferences
            )
            quants = quant_dim.compatible_quants(profile, prefs)
            max_steps = cfg.max_steps if cfg else 4
            extras = []
            for q in quants[:max_steps]:
                if q == base.quant:
                    continue
                extras.append(quant_dim.with_quant(base, q, from_quant=plan.quant))
            if strategy == CascadeStrategy.SEQUENTIAL:
                pool.extend(extras[:1])
            else:
                pool.extend(extras)

        if FallbackDimension.CONTEXT_LENGTH in dims:
            cfg = config_for(list(policy.dimensions), FallbackDimension.CONTEXT_LENGTH)
            prefs = (
                list(cfg.preferences)
                if cfg and cfg.preferences
                else policy.context_preferences
            )
            ctx = context_dim.suggest_context(
                profile, signals.context_tokens_needed, prefs
            )
            if ctx != base.context_length:
                pool.append(context_dim.with_context(base, ctx))

        if FallbackDimension.THREAD_COUNT in dims:
            cfg = config_for(list(policy.dimensions), FallbackDimension.THREAD_COUNT)
            prefs = (
                list(cfg.preferences)
                if cfg and cfg.preferences
                else policy.thread_preferences
            )
            thr = threads_dim.suggest_threads(
                signals.thread_available, plan.thread_count, prefs
            )
            if thr != base.thread_count:
                pool.append(threads_dim.with_threads(base, thr))

        if FallbackDimension.REASONING_BUDGET in dims:
            cfg = config_for(list(policy.dimensions), FallbackDimension.REASONING_BUDGET)
            prefs = (
                list(cfg.preferences)
                if cfg and cfg.preferences
                else policy.reasoning_preferences
            )
            rb = reasoning_dim.suggest_reasoning_budget(
                plan.reasoning_budget, signals.reasoning_tokens_needed, prefs
            )
            if rb != base.reasoning_budget:
                pool.append(reasoning_dim.with_reasoning(base, rb))

        if FallbackDimension.TOOL_USAGE in dims and policy.allow_tool_disable:
            if plan.tools_enabled and not signals.tools_required:
                dims_changed = list(base.dimensions_changed)
                if FallbackDimension.TOOL_USAGE not in dims_changed:
                    dims_changed.append(FallbackDimension.TOOL_USAGE)
                pool.append(
                    base.model_copy(
                        update={
                            "tools_enabled": False,
                            "dimensions_changed": dims_changed,
                            "quality_delta": base.quality_delta - 0.05,
                            "reason": f"{base.reason};tools=off".strip(";"),
                        }
                    )
                )

        if FallbackDimension.CASCADE in dims:
            for strat in CascadeStrategy:
                if strat == base.cascade_strategy:
                    continue
                dims_changed = list(base.dimensions_changed)
                if FallbackDimension.CASCADE not in dims_changed:
                    dims_changed.append(FallbackDimension.CASCADE)
                pool.append(
                    base.model_copy(
                        update={
                            "cascade_strategy": strat,
                            "dimensions_changed": dims_changed,
                            "reason": f"{base.reason};cascade={strat.value}".strip(";"),
                        }
                    )
                )
                break  # one cascade alternative enough for sequential

        return pool


def _param(plan: ExecutionSnapshot, profile: ModelProfile) -> float:
    # Prefer catalog later; use profile itself when comparing same
    return profile.parameter_count if plan.model == profile.model_id else 8.0


def _latency_hint(plan: ExecutionSnapshot, profile: ModelProfile) -> float:
    return profile.estimated_latency if plan.model == profile.model_id else 100.0
