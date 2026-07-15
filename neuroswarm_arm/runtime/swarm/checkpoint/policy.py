"""Checkpoint policy evaluation — decide whether to create, never execute tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .events import EventBus
from .exceptions import PolicyError
from .metrics import CheckpointMetrics
from .models import PolicyKind, WorkflowObservation

Predicate = Callable[[WorkflowObservation], bool]


@dataclass(frozen=True)
class CheckpointPolicy:
    """Configurable checkpoint trigger policy."""

    kind: PolicyKind
    n: int | None = None
    predicate: Predicate | None = field(default=None, compare=False, hash=False)
    predicate_id: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def always() -> CheckpointPolicy:
        return CheckpointPolicy(kind=PolicyKind.ALWAYS)

    @staticmethod
    def every_n_nodes(n: int) -> CheckpointPolicy:
        if n < 1:
            raise PolicyError("every_n_nodes requires n >= 1")
        return CheckpointPolicy(kind=PolicyKind.EVERY_N_NODES, n=n)

    @staticmethod
    def every_n_seconds(n: int) -> CheckpointPolicy:
        if n < 1:
            raise PolicyError("every_n_seconds requires n >= 1")
        return CheckpointPolicy(kind=PolicyKind.EVERY_N_SECONDS, n=n)

    @staticmethod
    def before_tool() -> CheckpointPolicy:
        return CheckpointPolicy(kind=PolicyKind.BEFORE_TOOL)

    @staticmethod
    def after_tool() -> CheckpointPolicy:
        return CheckpointPolicy(kind=PolicyKind.AFTER_TOOL)

    @staticmethod
    def before_aggregation() -> CheckpointPolicy:
        return CheckpointPolicy(kind=PolicyKind.BEFORE_AGGREGATION)

    @staticmethod
    def manual() -> CheckpointPolicy:
        return CheckpointPolicy(kind=PolicyKind.MANUAL)

    @staticmethod
    def custom(predicate: Predicate, *, predicate_id: str | None = None) -> CheckpointPolicy:
        return CheckpointPolicy(
            kind=PolicyKind.CUSTOM,
            predicate=predicate,
            predicate_id=predicate_id,
        )


class PolicyEngine:
    """Evaluate checkpoint policies against workflow observations."""

    def __init__(
        self,
        policies: list[CheckpointPolicy] | None = None,
        *,
        events: EventBus | None = None,
        metrics: CheckpointMetrics | None = None,
    ) -> None:
        self.policies = list(policies or [CheckpointPolicy.always()])
        self.events = events or EventBus()
        self.metrics = metrics or CheckpointMetrics()

    def should_checkpoint(self, observation: WorkflowObservation) -> bool:
        self.metrics.incr("policy_evaluations")
        for policy in self.policies:
            if not policy.enabled:
                continue
            if self._match(policy, observation):
                self.metrics.incr("policy_triggers")
                return True
        return False

    def _match(self, policy: CheckpointPolicy, obs: WorkflowObservation) -> bool:
        kind = policy.kind
        if kind == PolicyKind.ALWAYS:
            return True
        if kind == PolicyKind.MANUAL:
            return obs.event_kind == "manual"
        if kind == PolicyKind.EVERY_N_NODES:
            n = policy.n or 1
            return obs.nodes_since_checkpoint >= n
        if kind == PolicyKind.EVERY_N_SECONDS:
            n = policy.n or 1
            return obs.seconds_since_checkpoint >= float(n)
        if kind == PolicyKind.BEFORE_TOOL:
            return obs.event_kind == "before_tool"
        if kind == PolicyKind.AFTER_TOOL:
            return obs.event_kind == "after_tool"
        if kind == PolicyKind.BEFORE_AGGREGATION:
            return obs.event_kind == "before_aggregation"
        if kind == PolicyKind.CUSTOM:
            if policy.predicate is None:
                raise PolicyError("custom policy requires predicate")
            return bool(policy.predicate(obs))
        raise PolicyError(f"unknown policy kind: {kind}")
