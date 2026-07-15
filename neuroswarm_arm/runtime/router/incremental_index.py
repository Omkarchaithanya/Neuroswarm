"""Incremental vector index updates for tool embeddings."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from .embedding_service import EmbeddingService
from .models import ToolRecord
from .router_events import RouterEventBus, RouterEventKind


class IncrementalIndexer:
    def __init__(
        self,
        index: Any,
        embedder: EmbeddingService,
        *,
        events: RouterEventBus | None = None,
    ) -> None:
        self.index = index
        self.embedder = embedder
        self.events = events
        self._lock = threading.RLock()
        self._pending_compact = 0

    def upsert(self, tool: ToolRecord) -> np.ndarray:
        text = tool.index_text()
        vector = self.embedder.encode(text)
        with self._lock:
            self.index.update(tool.id, vector)
            self._pending_compact += 1
            if self._pending_compact >= 32:
                self.compact()
        if self.events:
            self.events.emit(RouterEventKind.INDEX_INCREMENTAL, tool_id=tool.id)
        return vector

    def remove(self, tool_id: str) -> bool:
        with self._lock:
            ok = self.index.delete(tool_id)
            self._pending_compact += 1
        return bool(ok)

    def rebuild(self, tools: list[ToolRecord]) -> int:
        with self._lock:
            self.index.clear()
            if not tools:
                return 0
            texts = [t.index_text() for t in tools]
            vectors = self.embedder.encode_batch(texts)
            keys = [t.id for t in tools]
            self.index.batch_insert(keys, vectors)
            self._pending_compact = 0
        if self.events:
            self.events.emit(RouterEventKind.INDEX_REBUILT, count=len(tools))
        return len(tools)

    def compact(self) -> None:
        with self._lock:
            self.index.compact()
            self._pending_compact = 0
