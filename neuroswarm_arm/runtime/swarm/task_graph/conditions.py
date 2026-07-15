"""Composable execution conditions for Task Graph nodes and edges."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .enums import ConditionKind, NodeStatus, SUCCESS_STATUSES
from .exceptions import ConditionError
from .interfaces import ICondition


ConditionPredicate = Callable[[Mapping[str, Any]], bool]

_CUSTOM_REGISTRY: dict[str, ConditionPredicate] = {}


def register_condition(name: str, predicate: ConditionPredicate) -> None:
    _CUSTOM_REGISTRY[name] = predicate


def unregister_condition(name: str) -> None:
    _CUSTOM_REGISTRY.pop(name, None)


def clear_condition_registry() -> None:
    _CUSTOM_REGISTRY.clear()


class BaseCondition:
    kind: ConditionKind

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value}

    def __and__(self, other: BaseCondition) -> And:
        return And(self, other)

    def __or__(self, other: BaseCondition) -> Or:
        return Or(self, other)

    def __invert__(self) -> Not:
        return Not(self)


class Always(BaseCondition):
    kind = ConditionKind.ALWAYS

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        return True


class Never(BaseCondition):
    kind = ConditionKind.NEVER

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        return False


class Success(BaseCondition):
    """True when named dependency nodes all succeeded."""

    kind = ConditionKind.SUCCESS

    def __init__(self, *node_ids: str) -> None:
        self.node_ids = node_ids

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        statuses: Mapping[str, Any] = ctx.get("node_statuses", {})
        if not self.node_ids:
            return True
        for nid in self.node_ids:
            st = statuses.get(nid)
            if isinstance(st, NodeStatus):
                if st not in SUCCESS_STATUSES:
                    return False
            elif st not in {s.value for s in SUCCESS_STATUSES}:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "node_ids": list(self.node_ids)}


class Failure(BaseCondition):
    kind = ConditionKind.FAILURE

    def __init__(self, *node_ids: str) -> None:
        self.node_ids = node_ids

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        statuses: Mapping[str, Any] = ctx.get("node_statuses", {})
        fail = {NodeStatus.FAILED, NodeStatus.TIMED_OUT, NodeStatus.CANCELLED}
        fail_vals = {s.value for s in fail}
        for nid in self.node_ids:
            st = statuses.get(nid)
            if isinstance(st, NodeStatus):
                if st in fail:
                    return True
            elif st in fail_vals:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "node_ids": list(self.node_ids)}


class ConfidenceThreshold(BaseCondition):
    kind = ConditionKind.CONFIDENCE_THRESHOLD

    def __init__(self, threshold: float, *, key: str = "confidence") -> None:
        self.threshold = threshold
        self.key = key

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        val = ctx.get(self.key)
        if val is None:
            return False
        return float(val) >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "threshold": self.threshold, "key": self.key}


class BudgetThreshold(BaseCondition):
    kind = ConditionKind.BUDGET_THRESHOLD

    def __init__(self, max_cost_usd: float) -> None:
        self.max_cost_usd = max_cost_usd

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        budget = ctx.get("budget", {})
        used = float(budget.get("cost_usd_used", 0.0)) if isinstance(budget, Mapping) else 0.0
        return used <= self.max_cost_usd

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "max_cost_usd": self.max_cost_usd}


class LatencyThreshold(BaseCondition):
    kind = ConditionKind.LATENCY_THRESHOLD

    def __init__(self, max_latency_ms: float) -> None:
        self.max_latency_ms = max_latency_ms

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        used = ctx.get("latency_ms_used")
        if used is None:
            budget = ctx.get("budget", {})
            used = budget.get("latency_ms_used", 0.0) if isinstance(budget, Mapping) else 0.0
        return float(used) <= self.max_latency_ms

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "max_latency_ms": self.max_latency_ms}


class MemoryThreshold(BaseCondition):
    kind = ConditionKind.MEMORY_THRESHOLD

    def __init__(self, max_pressure: float) -> None:
        self.max_pressure = max_pressure

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        pressure = float(ctx.get("memory_pressure", 0.0))
        return pressure <= self.max_pressure

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "max_pressure": self.max_pressure}


class ToolAvailability(BaseCondition):
    kind = ConditionKind.TOOL_AVAILABILITY

    def __init__(self, *tools: str) -> None:
        self.tools = tools

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        available = set(ctx.get("available_tools", set()))
        return all(t in available for t in self.tools)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "tools": list(self.tools)}


class ModelAvailability(BaseCondition):
    kind = ConditionKind.MODEL_AVAILABILITY

    def __init__(self, *models: str) -> None:
        self.models = models

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        available = set(ctx.get("available_models", set()))
        return all(m in available for m in self.models)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "models": list(self.models)}


class Custom(BaseCondition):
    kind = ConditionKind.CUSTOM

    def __init__(
        self,
        name: str,
        predicate: ConditionPredicate | None = None,
    ) -> None:
        self.name = name
        self._predicate = predicate
        if predicate is not None:
            register_condition(name, predicate)

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        pred = self._predicate or _CUSTOM_REGISTRY.get(self.name)
        if pred is None:
            raise ConditionError(f"custom condition not registered: {self.name}")
        return bool(pred(ctx))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "name": self.name}


class And(BaseCondition):
    kind = ConditionKind.AND

    def __init__(self, *children: BaseCondition) -> None:
        self.children = children

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        return all(c.evaluate(ctx) for c in self.children)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "children": [c.to_dict() for c in self.children]}


class Or(BaseCondition):
    kind = ConditionKind.OR

    def __init__(self, *children: BaseCondition) -> None:
        self.children = children

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        return any(c.evaluate(ctx) for c in self.children)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "children": [c.to_dict() for c in self.children]}


class Not(BaseCondition):
    kind = ConditionKind.NOT

    def __init__(self, child: BaseCondition) -> None:
        self.child = child

    def evaluate(self, ctx: Mapping[str, Any]) -> bool:
        return not self.child.evaluate(ctx)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "child": self.child.to_dict()}


_KIND_MAP: dict[str, type[BaseCondition]] = {
    ConditionKind.ALWAYS.value: Always,
    ConditionKind.NEVER.value: Never,
}


def condition_from_dict(data: Mapping[str, Any] | None) -> BaseCondition:
    if not data:
        return Always()
    kind = data.get("kind", ConditionKind.ALWAYS.value)
    if kind == ConditionKind.ALWAYS.value:
        return Always()
    if kind == ConditionKind.NEVER.value:
        return Never()
    if kind == ConditionKind.SUCCESS.value:
        return Success(*data.get("node_ids", []))
    if kind == ConditionKind.FAILURE.value:
        return Failure(*data.get("node_ids", []))
    if kind == ConditionKind.CONFIDENCE_THRESHOLD.value:
        return ConfidenceThreshold(float(data["threshold"]), key=data.get("key", "confidence"))
    if kind == ConditionKind.BUDGET_THRESHOLD.value:
        return BudgetThreshold(float(data["max_cost_usd"]))
    if kind == ConditionKind.LATENCY_THRESHOLD.value:
        return LatencyThreshold(float(data["max_latency_ms"]))
    if kind == ConditionKind.MEMORY_THRESHOLD.value:
        return MemoryThreshold(float(data["max_pressure"]))
    if kind == ConditionKind.TOOL_AVAILABILITY.value:
        return ToolAvailability(*data.get("tools", []))
    if kind == ConditionKind.MODEL_AVAILABILITY.value:
        return ModelAvailability(*data.get("models", []))
    if kind == ConditionKind.CUSTOM.value:
        return Custom(str(data["name"]))
    if kind == ConditionKind.AND.value:
        return And(*(condition_from_dict(c) for c in data.get("children", [])))
    if kind == ConditionKind.OR.value:
        return Or(*(condition_from_dict(c) for c in data.get("children", [])))
    if kind == ConditionKind.NOT.value:
        return Not(condition_from_dict(data["child"]))
    raise ConditionError(f"unknown condition kind: {kind}")


def evaluate_condition(
    condition: BaseCondition | Mapping[str, Any] | None,
    ctx: Mapping[str, Any],
) -> bool:
    if condition is None:
        return True
    if isinstance(condition, Mapping):
        condition = condition_from_dict(condition)
    if not isinstance(condition, BaseCondition) and not isinstance(condition, ICondition):
        raise ConditionError(f"invalid condition type: {type(condition)}")
    return bool(condition.evaluate(ctx))
