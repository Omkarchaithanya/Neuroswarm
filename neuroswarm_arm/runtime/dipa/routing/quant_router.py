"""Quantization resolution via AQR connector (DIPA asks, never owns tables)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from ..interfaces.types import ExecutionPlan, InferenceRequest

if TYPE_CHECKING:
    from ..interfaces.quantizer import IQuantConnector


class QuantRouter:
    """Resolve quant level for a request/plan through :class:`IQuantConnector`."""

    def __init__(self, aqr_connector: IQuantConnector) -> None:
        self.connector = aqr_connector

    def resolve(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        *,
        constraints: Mapping[str, Any] | None = None,
    ) -> str:
        merged: dict[str, Any] = {
            "model": plan.model,
            "backend": plan.backend,
            "latency_sla_ms": plan.latency_sla_ms,
            "cost_budget_usd": plan.cost_budget_usd,
            "stream": plan.stream,
        }
        if constraints:
            merged.update(dict(constraints))

        quant = self.connector.choose(req, plan.workload, constraints=merged)
        if not quant:
            quant = plan.quant or "Q5_K_M"
        if not self.connector.is_supported(quant):
            available = self.connector.available()
            quant = available[0] if available else (plan.quant or "Q5_K_M")

        plan.quant = str(quant)
        plan.metadata.setdefault("quant", {})
        plan.metadata["quant"]["resolved"] = plan.quant
        return plan.quant
