"""Stage span helpers — semantic spine for NEXUS-ARM request lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from .schemas import AttributeKeys, SpanNames


class SpanHelper:
    """Thin helpers over IROF/tracer for mandatory stage spans."""

    def __init__(self, rof: Any) -> None:
        self.rof = rof

    @contextmanager
    def stage(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        with self.rof.span(name, attributes=attributes) as span:
            yield span

    def admission(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.ADMISSION, attributes=attrs)

    def policy(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.POLICY, attributes=attrs)

    def budget(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.BUDGET, attributes=attrs)

    def planner(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.PLANNER, attributes=attrs)

    def routing(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.ROUTING, attributes=attrs)

    def haoe_workflow(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.HAOE_WORKFLOW, attributes=attrs)

    def dipa_infer(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.DIPA_INFER, attributes=attrs)

    def backend(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.BACKEND, attributes=attrs)

    def streaming(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.STREAMING, attributes=attrs)

    def quant(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.QUANT, attributes=attrs)

    def warm(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.WARM, attributes=attrs)

    def kv(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.KV, attributes=attrs)

    def cost(self, **attrs: Any) -> Any:
        return self.stage(SpanNames.COST, attributes=attrs)


def decision_attributes(
    *,
    tier: int | None = None,
    backend: str = "",
    model: str = "",
    quant: str = "",
    envelope_id: str = "",
    numa_node: int | None = None,
    cost_estimate: float | None = None,
    budget_remaining: float | None = None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if tier is not None:
        attrs["nexus.model_tier"] = tier
    if backend:
        attrs[AttributeKeys.BACKEND_ID] = backend
    if model:
        attrs[AttributeKeys.MODEL_ID] = model
    if quant:
        attrs[AttributeKeys.QUANTIZATION] = quant
    if envelope_id:
        attrs[AttributeKeys.ENVELOPE_ID] = envelope_id
    if numa_node is not None:
        attrs[AttributeKeys.NUMA_NODE] = numa_node
    if cost_estimate is not None:
        attrs[AttributeKeys.COST_ESTIMATE] = cost_estimate
    if budget_remaining is not None:
        attrs[AttributeKeys.BUDGET_REMAINING] = budget_remaining
    return attrs
