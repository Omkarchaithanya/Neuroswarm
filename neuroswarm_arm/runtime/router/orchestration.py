"""Explicit router → cost → inference hints (no second HTTP cascade client)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .cost_router import CostDecision, CostRouter
from .models import RoutingResult
from .tool_schema_builder import estimate_schema_tokens


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
    tool_search_mode: Literal["pass_through", "bridge"] = "pass_through"
    tool_search_listing_truncated: bool = False

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
            "tool_search_mode": self.tool_search_mode,
            "tool_search_listing_truncated": self.tool_search_listing_truncated,
        }


def build_routed_inference_hints(
    query: str,
    route_result: RoutingResult,
    *,
    prompt_block: str = "",
    schemas: list[dict[str, Any]] | None = None,
    cost_router: CostRouter | None = None,
    plan_state: dict[str, Any] | None = None,
    tool_search_cfg: Any | None = None,
    registry: Any | None = None,
    context_length: int | None = None,
) -> RoutedInferenceHints:
    """Sequence: semantic route result → CostRouter → payload hints for DIPA.

    Callers must pass only top-K schemas/prompt_block (never the full catalog).
    When ``tool_search_cfg`` is None, behavior is byte-identical to pre-tool_search.
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

    prompt = prompt_block or ""
    mode: Literal["pass_through", "bridge"] = "pass_through"
    listing_truncated = False

    if tool_search_cfg is not None:
        from .tool_search import (
            BRIDGE_TOOL_SCHEMA,
            build_listing_manifest,
            decide_mode,
        )
        from .tool_search.metrics import record_mode, record_truncated

        initial_ids = set()
        for scored in tools[:top_k]:
            tool = getattr(scored, "tool", scored)
            tid = getattr(tool, "id", None) or getattr(tool, "name", None)
            if tid:
                initial_ids.add(str(tid))

        catalog: list[Any] = []
        if registry is not None and hasattr(registry, "as_list"):
            catalog = list(registry.as_list())
        elif registry is not None and isinstance(registry, (list, tuple)):
            catalog = list(registry)

        deferred = []
        for tool in catalog:
            tid = str(getattr(tool, "id", "") or getattr(tool, "name", "") or "")
            if tid and tid not in initial_ids:
                deferred.append(tool)

        deferred_tokens = 0
        for tool in deferred:
            schema = getattr(tool, "input_schema", None) or {}
            if not isinstance(schema, dict):
                schema = {"name": getattr(tool, "name", ""), "description": getattr(tool, "description", "")}
            else:
                schema = {
                    "name": getattr(tool, "name", ""),
                    "description": getattr(tool, "description", ""),
                    "parameters": schema,
                }
            deferred_tokens += estimate_schema_tokens(schema)

        ctx_len = int(context_length) if context_length is not None else max(before, 8192)
        mode = decide_mode(
            enabled=str(getattr(tool_search_cfg, "enabled", "auto")),
            threshold_pct=float(getattr(tool_search_cfg, "threshold_pct", 10.0)),
            context_length=ctx_len,
            deferred_schema_tokens=deferred_tokens,
            has_deferrable=bool(deferred),
        )
        record_mode(mode)
        if mode == "bridge":
            schema_list = [BRIDGE_TOOL_SCHEMA]
            listing = str(getattr(tool_search_cfg, "listing", "auto"))
            if listing in {"auto", "on"}:
                prompt, listing_truncated = build_listing_manifest(
                    catalog if catalog else deferred,
                    int(getattr(tool_search_cfg, "listing_max_tokens", 20000)),
                )
            else:
                prompt = ""
            if listing_truncated:
                record_truncated()
            # Bridge ships zero deferrable schemas — names stay as routed top-K for metrics.
            decision = CostDecision(
                tier=decision.tier,
                quant=decision.quant,
                reason=decision.reason,
                tool_search_mode="bridge",
            )
        else:
            decision = CostDecision(
                tier=decision.tier,
                quant=decision.quant,
                reason=decision.reason,
                tool_search_mode="pass_through",
            )

    return RoutedInferenceHints(
        tool_names=names,
        tool_schemas=schema_list,
        tool_prompt_block=prompt,
        tool_confidence=conf,
        high_confidence=high,
        cost_decision=decision,
        prompt_tokens_before=before,
        prompt_tokens_after=after,
        schema_token_reduction=reduction,
        tool_search_mode=mode,
        tool_search_listing_truncated=listing_truncated,
    )
