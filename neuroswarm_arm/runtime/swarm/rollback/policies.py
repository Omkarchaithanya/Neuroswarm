"""Rollback policies — decide whether to roll back (no execution)."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from pydantic import Field

from .events import EventBus
from .exceptions import PolicyError
from .interfaces import IPolicyPredicatePort
from .metrics import RollbackMetrics
from .models import PolicyKind, RollbackObservation, _Frozen


class RollbackPolicy(_Frozen):
    """Configurable rollback trigger policy."""

    kind: PolicyKind
    name: str = ""
    enabled: bool = True
    threshold: float | None = None
    budget_floor: float | None = None
    latency_ms_ceiling: float | None = None
    failure_count_threshold: int | None = None
    predicate_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def evaluate(self, observation: RollbackObservation) -> bool:
        if not self.enabled:
            return False
        if self.kind == PolicyKind.ALWAYS:
            return True
        if self.kind == PolicyKind.MANUAL:
            return bool(observation.manual)
        if self.kind == PolicyKind.AUTOMATIC:
            return observation.event_kind in {"failure", "partial_failure", "timeout"}
        if self.kind == PolicyKind.THRESHOLD:
            if self.threshold is None:
                raise PolicyError("threshold policy requires threshold")
            obs_threshold = (
                observation.threshold
                if observation.threshold is not None
                else float(observation.failure_count)
            )
            return obs_threshold >= self.threshold
        if self.kind == PolicyKind.BUDGET:
            if self.budget_floor is None:
                raise PolicyError("budget policy requires budget_floor")
            remaining = observation.budget_remaining
            if remaining is None:
                return False
            return remaining <= self.budget_floor
        if self.kind == PolicyKind.LATENCY:
            if self.latency_ms_ceiling is None:
                raise PolicyError("latency policy requires latency_ms_ceiling")
            return observation.latency_ms >= self.latency_ms_ceiling
        if self.kind == PolicyKind.FAILURE:
            threshold = self.failure_count_threshold or 1
            return observation.failure_count >= threshold
        if self.kind == PolicyKind.CUSTOM:
            # Custom requires PolicyEngine with predicate port
            return False
        return False


class PolicyEngine:
    """Evaluate rollback policies against observations."""

    def __init__(
        self,
        policies: Sequence[RollbackPolicy] | None = None,
        *,
        events: EventBus | None = None,
        metrics: RollbackMetrics | None = None,
        predicate_port: IPolicyPredicatePort | None = None,
        custom_predicates: Mapping[str, Callable[[RollbackObservation], bool]]
        | None = None,
    ) -> None:
        self.policies = list(policies or [])
        self.events = events or EventBus()
        self.metrics = metrics or RollbackMetrics()
        self.predicate_port = predicate_port
        self.custom_predicates = dict(custom_predicates or {})

    def add(self, policy: RollbackPolicy) -> None:
        self.policies.append(policy)

    def should_rollback(self, observation: RollbackObservation) -> bool:
        self.metrics.incr("policy_evaluations")
        for policy in self.policies:
            if self._eval(policy, observation):
                self.metrics.incr("policy_triggers")
                return True
        return False

    def matching(self, observation: RollbackObservation) -> list[RollbackPolicy]:
        self.metrics.incr("policy_evaluations")
        matched: list[RollbackPolicy] = []
        for policy in self.policies:
            if self._eval(policy, observation):
                matched.append(policy)
                self.metrics.incr("policy_triggers")
        return matched

    def _eval(self, policy: RollbackPolicy, observation: RollbackObservation) -> bool:
        if policy.kind == PolicyKind.CUSTOM:
            if policy.predicate_id and policy.predicate_id in self.custom_predicates:
                return bool(self.custom_predicates[policy.predicate_id](observation))
            if self.predicate_port and policy.predicate_id:
                return self.predicate_port.evaluate_predicate(
                    policy.predicate_id,
                    observation.model_dump(mode="json"),
                )
            raise PolicyError(
                f"custom policy {policy.name or policy.predicate_id} has no predicate"
            )
        return policy.evaluate(observation)


def always_rollback(*, name: str = "always") -> RollbackPolicy:
    return RollbackPolicy(kind=PolicyKind.ALWAYS, name=name)


def manual_rollback(*, name: str = "manual") -> RollbackPolicy:
    return RollbackPolicy(kind=PolicyKind.MANUAL, name=name)


def automatic_rollback(*, name: str = "automatic") -> RollbackPolicy:
    return RollbackPolicy(kind=PolicyKind.AUTOMATIC, name=name)


def threshold_rollback(threshold: float, *, name: str = "threshold") -> RollbackPolicy:
    return RollbackPolicy(kind=PolicyKind.THRESHOLD, name=name, threshold=threshold)


def budget_rollback(budget_floor: float, *, name: str = "budget") -> RollbackPolicy:
    return RollbackPolicy(
        kind=PolicyKind.BUDGET, name=name, budget_floor=budget_floor
    )


def latency_rollback(
    latency_ms_ceiling: float, *, name: str = "latency"
) -> RollbackPolicy:
    return RollbackPolicy(
        kind=PolicyKind.LATENCY,
        name=name,
        latency_ms_ceiling=latency_ms_ceiling,
    )


def failure_rollback(
    failure_count_threshold: int = 1, *, name: str = "failure"
) -> RollbackPolicy:
    return RollbackPolicy(
        kind=PolicyKind.FAILURE,
        name=name,
        failure_count_threshold=failure_count_threshold,
    )


def custom_rollback(
    predicate_id: str, *, name: str = "custom"
) -> RollbackPolicy:
    return RollbackPolicy(
        kind=PolicyKind.CUSTOM, name=name, predicate_id=predicate_id
    )
