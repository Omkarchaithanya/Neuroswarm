<<<<<<< HEAD
"""Backward-compatible SemanticMCPRouter facade over runtime.router."""

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
<<<<<<< HEAD

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
=======
import math

from ..schemas import ToolDef
from .registry import ToolRegistry

try:
    import faiss  # type: ignore
    import numpy as np  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    faiss = None
    np = None
    SentenceTransformer = None


def _simple_embed(text: str, dims: int = 16) -> list[float]:
    vec = [0.0] * dims
    for idx, ch in enumerate(text.lower()):
        vec[idx % dims] += (ord(ch) % 31) / 31.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84


@dataclass
class SemanticMCPRouter:
<<<<<<< HEAD
    """Compat wrapper. Prefer SemanticToolRouter / build_router() for new code."""

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
    registry: ToolRegistry
    top_k: int = 3
    threshold: float = 0.42
    encoder_name: str = "BAAI/bge-small-en-v1.5"
<<<<<<< HEAD
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
=======
    _index: Any = field(default=None, init=False, repr=False)
    _model: Any = field(default=None, init=False, repr=False)
    _tool_ids: list[str] = field(default_factory=list, init=False)

    def _ensure_backend(self) -> None:
        if faiss is not None and self._index is None:
            self._index = faiss.IndexFlatIP(16)
        if SentenceTransformer is not None and self._model is None:
            self._model = SentenceTransformer(self.encoder_name, device="cpu")

    def _embed(self, text: str) -> list[float]:
        self._ensure_backend()
        if self._model is not None and np is not None:
            arr = self._model.encode(text, normalize_embeddings=True)
            vec = list(arr)
            if len(vec) < 16:
                vec.extend([0.0] * (16 - len(vec)))
            return vec[:16]
        return _simple_embed(text)

    def index_tools(self) -> None:
        self._ensure_backend()
        self._tool_ids = []
        if self._index is not None:
            self._index.reset()
        for tool in self.registry.as_list():
            text = f"{tool.name} {tool.description} {' '.join(tool.params.keys())}"
            emb = self._embed(text)
            self._tool_ids.append(tool.id)
            if self._index is not None and np is not None:
                self._index.add(np.array([emb], dtype="float32"))

    def route(self, query: str) -> list[ToolDef]:
        tools = self.registry.as_list()
        if not tools:
            return []
        if self._index is None or not self._tool_ids:
            scored = []
            for tool in tools:
                score = sum(1 for token in query.lower().split() if token in tool.description.lower() or token in tool.name.lower())
                scored.append((score, tool))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [tool for _, tool in scored[: self.top_k]]
        q = self._embed(query)
        if np is None:
            return tools[: self.top_k]
        distances, indices = self._index.search(np.array([q], dtype="float32"), self.top_k)
        picked: list[ToolDef] = []
        for idx in indices[0]:
            if idx < 0:
                continue
            picked.append(self.registry.tools[self._tool_ids[idx]])
        return picked
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
