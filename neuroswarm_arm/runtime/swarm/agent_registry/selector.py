"""Weighted deterministic agent selector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable

from ._utils import stable_hash
from .agent import Agent
from .exceptions import SelectionError
from .lifecycle import LifecycleState, is_selectable
from .models import ScoredAgent, ScoringWeights, SelectionRequest, SelectionResult
from .scoring import score_agent

if TYPE_CHECKING:
    from .cache import RegistryCache
    from .events import EventBus
    from .metrics import RegistryMetrics


class AgentSelector:
    """Select best matching agents via hard filters + weighted scores."""

    def __init__(
        self,
        *,
        weights: ScoringWeights | None = None,
        cache: RegistryCache | None = None,
        events: EventBus | None = None,
        metrics: RegistryMetrics | None = None,
    ) -> None:
        self.weights = (weights or ScoringWeights()).normalized()
        self.cache = cache
        self.events = events
        self.metrics = metrics

    def select(
        self,
        agents: Iterable[Agent],
        request: SelectionRequest,
        *,
        use_cache: bool = True,
    ) -> SelectionResult:
        req_hash = stable_hash(request.model_dump(mode="json"))
        if use_cache and self.cache is not None:
            cached = self.cache.get("selection", req_hash)
            if cached is not None:
                return cached

        candidates = list(agents)
        rejected: list[dict] = []
        eligible: list[Agent] = []

        for agent in candidates:
            ok, reason = self._hard_filter(agent, request)
            if not ok:
                rejected.append({"agent_id": agent.id, "name": agent.name, "reason": reason})
                continue
            eligible.append(agent)

        scored: list[ScoredAgent] = []
        for agent in eligible:
            total, breakdown, reasons = score_agent(agent, request, weights=self.weights)
            scored.append(
                ScoredAgent(
                    agent_id=agent.id,
                    name=agent.name,
                    score=total,
                    breakdown=breakdown,
                    reasons=reasons,
                )
            )

        scored.sort(key=lambda s: (-s.score, s.name, s.agent_id))
        limited = scored[: request.limit]
        result = SelectionResult(
            request_hash=req_hash,
            agents=limited,
            rejected=rejected,
            metadata={"eligible": len(eligible), "total": len(candidates)},
        )

        if use_cache and self.cache is not None:
            self.cache.set("selection", req_hash, result)

        if self.metrics is not None:
            self.metrics.record_selection(candidates=len(eligible))

        if self.events is not None:
            from .events import SelectionPerformed

            self.events.emit(
                SelectionPerformed(
                    request_hash=req_hash,
                    selected=[s.agent_id for s in limited],
                    rejected_count=len(rejected),
                )
            )

        return result

    def select_best(
        self,
        agents: Iterable[Agent],
        request: SelectionRequest,
        *,
        require: bool = False,
    ) -> ScoredAgent | None:
        result = self.select(agents, request)
        if result.best is None and require:
            raise SelectionError("no eligible agents for selection request")
        return result.best

    def _hard_filter(self, agent: Agent, request: SelectionRequest) -> tuple[bool, str]:
        if agent.status is LifecycleState.DISABLED:
            return False, "disabled"
        if agent.status is LifecycleState.RETIRED:
            return False, "retired"
        if agent.status is LifecycleState.FAILED:
            return False, "failed"
        if agent.status is LifecycleState.CREATED:
            return False, "not_registered"
        if not request.include_busy and agent.status is LifecycleState.BUSY:
            return False, "busy"
        if not is_selectable(agent.status) and agent.status not in {
            LifecycleState.LOADED,
            LifecycleState.REGISTERED,
            LifecycleState.PAUSED,
            LifecycleState.RESTARTING,
        }:
            # LOADED/REGISTERED allowed only if explicitly ready-ish — require READY/BUSY
            if agent.status not in {LifecycleState.READY, LifecycleState.BUSY}:
                return False, f"lifecycle:{agent.status.value}"
        if agent.status not in {LifecycleState.READY, LifecycleState.BUSY}:
            return False, f"lifecycle:{agent.status.value}"

        if agent.health.score < request.min_health:
            return False, "health_below_min"
        if agent.confidence_score < request.min_confidence:
            return False, "confidence_below_min"

        if request.required_tools:
            have = set(agent.effective_tools())
            missing = [t for t in request.required_tools if t not in have]
            if missing:
                return False, f"missing_tools:{','.join(missing)}"

        if request.required_models:
            have = set(agent.effective_models())
            missing = [m for m in request.required_models if m not in have]
            if missing:
                return False, f"missing_models:{','.join(missing)}"

        if request.required_backends:
            have = {b.lower() for b in agent.effective_backends()}
            missing = [b for b in request.required_backends if b.lower() not in have]
            if missing:
                return False, f"missing_backends:{','.join(missing)}"

        if request.required_quantizations:
            have = {q.lower() for q in agent.effective_quants()}
            missing = [
                q for q in request.required_quantizations if q.lower() not in have
            ]
            if missing:
                return False, f"missing_quants:{','.join(missing)}"

        if request.budget.max_cost_usd is not None:
            if agent.estimated_cost > request.budget.max_cost_usd:
                return False, "cost_over_budget"
        if request.budget.max_latency_ms is not None:
            if agent.estimated_latency > request.budget.max_latency_ms:
                return False, "latency_over_budget"
        if request.budget.max_tokens is not None:
            if agent.estimated_tokens > request.budget.max_tokens:
                return False, "tokens_over_budget"
        if request.budget.max_memory_bytes is not None:
            mem = agent.estimated_memory or agent.resource_requirements.memory_bytes
            if mem > request.budget.max_memory_bytes:
                return False, "memory_over_budget"

        return True, "ok"
