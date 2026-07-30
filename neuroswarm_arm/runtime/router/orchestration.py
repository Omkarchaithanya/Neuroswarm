"""Explicit router → cost → inference hints (no second HTTP cascade client)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cost_router import CostDecision, CostRouter
from .models import RoutingResult


@dataclass(slots=True)
class RoutedInferenceHints:
    tool_names: list[str] = field(default_factory=list)
    tool_schemas: list[dict[str, Any]] = field(default_factory=list)
    tool_prompt_block: str = ""
    tool_confidence: float = 0.0
    high_confidence: bool = False
    cost_decision: CostDecision | None = None
    prompt_tokens_before: int = 0
    prompt_tokens_after: int = 0
    schema_token_reduction: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        red = self.schema_token_reduction
        return {
            "tool_names": list(self.tool_names),
            "tool_confidence": self.tool_confidence,
            "high_confidence": self.high_confidence,
            "cost": self.cost_decision.as_dict() if self.cost_decision else {},
            "prompt_tokens_before": self.prompt_tokens_before,
            "prompt_tokens_after": self.prompt_tokens_after,
            "schema_token_reduction": red,
            "tool_prompt_chars": len(self.tool_prompt_block or ""),
            "tool_schema_count": len(self.tool_schemas),
        }


def build_routed_inference_hints(
    query: str,
    route_result: RoutingResult,
    *,
    prompt_block: str = "",
    schemas: list[dict[str, Any]] | None = None,
    cost_router: CostRouter | None = None,
    plan_state: dict[str, Any] | None = None,
) -> RoutedInferenceHints:
    """Sequence: semantic route result → CostRouter → payload hints for DIPA.

    Callers must pass only top-K schemas/prompt_block (never the full catalog).
    """
    tools = list(getattr(route_result, "tools", None) or [])
    names = []
    for scored in tools:
        tool = getattr(scored, "tool", None)
        name = getattr(tool, "name", None) or getattr(tool, "id", None)
        if name:
            names.append(str(name))
    conf = float(getattr(route_result, "confidence_top1", 0.0) or 0.0)
    high = bool(getattr(route_result, "high_confidence", False))
    before = int(getattr(route_result, "prompt_tokens_before", 0) or 0)
    after = int(getattr(route_result, "prompt_tokens_after", 0) or 0)
    reduction = 0.0
    if before > 0:
        reduction = max(0.0, min(1.0, 1.0 - (after / float(before))))

    router = cost_router or CostRouter()
    decision = router.route(query, tool_confidence=conf, plan_state=plan_state)

    schema_list = list(schemas or [])
    # Honesty: never silently expand beyond top_k from the route result.
    top_k = int(getattr(route_result, "top_k", 3) or 3)
    if len(schema_list) > top_k:
        schema_list = schema_list[:top_k]
    if len(names) > top_k:
        names = names[:top_k]

    return RoutedInferenceHints(
        tool_names=names,
        tool_schemas=schema_list,
        tool_prompt_block=prompt_block or "",
        tool_confidence=conf,
        high_confidence=high,
        cost_decision=decision,
        prompt_tokens_before=before,
        prompt_tokens_after=after,
        schema_token_reduction=reduction,
    )
