from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
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


@dataclass
class SemanticMCPRouter:
    registry: ToolRegistry
    top_k: int = 3
    threshold: float = 0.42
    encoder_name: str = "BAAI/bge-small-en-v1.5"
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
