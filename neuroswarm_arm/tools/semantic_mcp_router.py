"""Backward-compatible SemanticMCPRouter facade over runtime.router."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from neuroswarm_arm.runtime.router.models import RouteContext, RoutingResult, ToolRecord
from neuroswarm_arm.runtime.router.tool_router import SemanticToolRouter
from neuroswarm_arm.schemas import ToolDef

from .registry import ToolRegistry


def _to_tooldef(record: ToolRecord) -> ToolDef:
    return ToolDef(
        id=record.id,
        name=record.name,
        description=record.description,
        params=dict(record.params),
        endpoint=record.endpoint,
        auth=record.auth,
    )


@dataclass
class SemanticMCPRouter:
    """Compat wrapper. Prefer SemanticToolRouter / build_router() for new code."""

    registry: ToolRegistry
    top_k: int = 3
    threshold: float = 0.42
    encoder_name: str = "nomic-embed-text-v1.5"
    fallback_dims: int = 64
    _inner: SemanticToolRouter | None = field(default=None, repr=False)
    _route_context_extras: dict[str, Any] = field(default_factory=dict, repr=False)

    def bind(self, inner: SemanticToolRouter) -> SemanticToolRouter:
        self._inner = inner
        return inner

    @property
    def inner(self) -> SemanticToolRouter | None:
        return self._inner

    def index_tools(self) -> None:
        if self._inner is not None:
            self._inner.index_tools()
            return
        # Lazy bootstrap for benchmark scripts that only construct the facade
        self._ensure_inner()
        assert self._inner is not None
        self._inner.index_tools()

    def _ensure_inner(self) -> SemanticToolRouter:
        if self._inner is not None:
            return self._inner
        from neuroswarm_arm.runtime.router import build_router
        from neuroswarm_arm.runtime.router.router_config import RouterConfig

        cfg = RouterConfig(
            top_k=self.top_k,
            threshold=self.threshold,
            encoder_name=self.encoder_name,
            fallback_dims=self.fallback_dims,
            enable_hot_reload=False,
        )
        # Seed from legacy registry if populated
        router = build_router(cfg, start_sync=False)
        for tool in self.registry.as_list():
            if hasattr(tool, "model_dump"):
                data = tool.model_dump()
            elif hasattr(tool, "to_dict"):
                data = tool.to_dict()
            else:
                data = {
                    "id": tool.id,
                    "name": tool.name,
                    "description": tool.description,
                    "params": dict(getattr(tool, "params", {}) or {}),
                    "endpoint": getattr(tool, "endpoint", None),
                    "auth": getattr(tool, "auth", None),
                }
            router.register_tool(ToolRecord.from_dict(data))
        self._inner = router
        return router

    def build_context(self, request: Any, query: str) -> RouteContext:
        extras = dict(self._route_context_extras)
        return RouteContext(
            agent_id=str(getattr(request, "agent_id", "default") or "default"),
            agent_role=str(getattr(request, "agent_role", "tool_call") or "tool_call"),
            conversation_excerpt=query,
            memory_pressure=float(extras.get("memory_pressure", 0.0)),
            quantization=str(extras.get("quantization", "")),
            inference_tier=int(extras.get("inference_tier", 1)),
            budget_remaining_usd=float(extras.get("budget_remaining_usd", 1.0)),
            latency_slo_ms=float(extras.get("latency_slo_ms", 4000.0)),
            security_policies=list(extras.get("security_policies") or []),
        )

    def set_context_extras(self, **kwargs: Any) -> None:
        self._route_context_extras.update(kwargs)

    def route_result(self, query: str, context: RouteContext | None = None) -> RoutingResult:
        inner = self._ensure_inner()
        return inner.route(query, context=context, top_k=self.top_k)

    def route(self, query: str, context: RouteContext | None = None) -> list[ToolDef]:
        result = self.route_result(query, context=context)
        return [_to_tooldef(s.tool) for s in result.tools]

    def prompt_block(self, result: RoutingResult) -> str:
        return self._ensure_inner().prompt_block(result)

    def __getattr__(self, name: str) -> Any:
        inner = self._ensure_inner()
        return getattr(inner, name)
