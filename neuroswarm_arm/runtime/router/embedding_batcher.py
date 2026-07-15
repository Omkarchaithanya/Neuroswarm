"""Embedding batch scheduler."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Callable

import numpy as np

from .embedding_service import EmbeddingService


@dataclass
class BatchRequest:
    texts: list[str]
    event: threading.Event = field(default_factory=threading.Event)
    result: np.ndarray | None = None
    error: Exception | None = None


class EmbeddingBatcher:
    """Accumulates encode requests and flushes by size or latency budget."""

    def __init__(
        self,
        service: EmbeddingService,
        *,
        batch_size: int = 32,
        max_wait_ms: float = 8.0,
    ) -> None:
        self.service = service
        self.batch_size = batch_size
        self.max_wait_ms = max_wait_ms
        self._queue: deque[BatchRequest] = deque()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="emb-batcher", daemon=True)
        self._thread.start()

    def encode(self, texts: list[str] | str) -> np.ndarray:
        payload = [texts] if isinstance(texts, str) else list(texts)
        req = BatchRequest(texts=payload)
        with self._cv:
            self._queue.append(req)
            self._cv.notify()
        req.event.wait(timeout=30.0)
        if req.error is not None:
            raise req.error
        assert req.result is not None
        return req.result

    def _loop(self) -> None:
        while self._running:
            with self._cv:
                if not self._queue:
                    self._cv.wait(timeout=self.max_wait_ms / 1000.0)
                if not self._queue:
                    continue
                batch: list[BatchRequest] = []
                total = 0
                started = time.perf_counter()
                while self._queue and total < self.batch_size:
                    item = self._queue.popleft()
                    batch.append(item)
                    total += len(item.texts)
                    if (time.perf_counter() - started) * 1000.0 >= self.max_wait_ms:
                        break
            texts: list[str] = []
            spans: list[tuple[BatchRequest, int]] = []
            for req in batch:
                spans.append((req, len(req.texts)))
                texts.extend(req.texts)
            try:
                vectors = self.service.encode_batch(texts)
                offset = 0
                for req, n in spans:
                    req.result = vectors[offset : offset + n]
                    offset += n
                    req.event.set()
            except Exception as exc:
                for req, _ in spans:
                    req.error = exc
                    req.event.set()

    def shutdown(self) -> None:
        self._running = False
        with self._cv:
            self._cv.notify_all()
        self._thread.join(timeout=2.0)


def batch_encode(
    service: EmbeddingService,
    texts: list[str],
    *,
    batch_size: int = 32,
    on_batch: Callable[[int, int], None] | None = None,
) -> np.ndarray:
    if not texts:
        return np.zeros((0, service.dims), dtype=np.float32)
    rows = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        rows.append(service.encode_batch(chunk))
        if on_batch:
            on_batch(i, len(texts))
    return np.vstack(rows)
