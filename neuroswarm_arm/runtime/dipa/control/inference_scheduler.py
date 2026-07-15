"""InferenceScheduler — admits work from queue onto execution workers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .request_queue import QueuedRequest, RequestQueue


class InferenceScheduler:
    def __init__(
        self,
        queue: RequestQueue,
        *,
        workers: int = 4,
        handler: Callable[[QueuedRequest], Any] | None = None,
    ) -> None:
        self.queue = queue
        self.workers = max(1, workers)
        self.handler = handler
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._inflight = 0
        self._lock = threading.Lock()
        self._completed = 0
        self._failed = 0

    def set_handler(self, handler: Callable[[QueuedRequest], Any]) -> None:
        self.handler = handler

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        for i in range(self.workers):
            t = threading.Thread(
                target=self._loop,
                name=f"dipa-sched-{i}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

    def stop(self, timeout_s: float = 10.0) -> None:
        self._stop.set()
        self.queue.close()
        deadline = time.time() + timeout_s
        for t in self._threads:
            remaining = max(0.0, deadline - time.time())
            t.join(timeout=remaining)
        self._threads.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            item = self.queue.dequeue(timeout_s=0.25)
            if item is None:
                continue
            if self.handler is None:
                continue
            with self._lock:
                self._inflight += 1
            try:
                self.handler(item)
                with self._lock:
                    self._completed += 1
            except Exception:
                with self._lock:
                    self._failed += 1
            finally:
                with self._lock:
                    self._inflight -= 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "workers": self.workers,
                "inflight": self._inflight,
                "completed": self._completed,
                "failed": self._failed,
                "queue": self.queue.snapshot(),
            }
