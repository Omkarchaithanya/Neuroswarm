"""Background embedding workers."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from queue import Empty, Queue
import threading
from typing import Callable

import numpy as np

from .embedding_service import EmbeddingService


@dataclass
class EmbedJob:
    job_id: str
    texts: list[str]
    callback: Callable[[str, np.ndarray], None] | None = None


@dataclass
class EmbeddingWorkerPool:
    service: EmbeddingService
    workers: int = 2
    _queue: Queue[EmbedJob | None] = field(default_factory=Queue)
    _executor: ThreadPoolExecutor | None = field(default=None, init=False)
    _threads: list[threading.Thread] = field(default_factory=list, init=False)
    _running: bool = field(default=False, init=False)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="emb-worker")
        for i in range(self.workers):
            t = threading.Thread(target=self._worker_loop, name=f"emb-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def submit(self, job: EmbedJob) -> None:
        if not self._running:
            self.start()
        self._queue.put(job)

    def encode_future(self, texts: list[str]) -> Future[np.ndarray]:
        if self._executor is None:
            self.start()
        assert self._executor is not None
        return self._executor.submit(self.service.encode_batch, texts)

    def _worker_loop(self) -> None:
        while self._running:
            try:
                job = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if job is None:
                break
            try:
                vectors = self.service.encode_batch(job.texts)
                if job.callback is not None:
                    job.callback(job.job_id, vectors)
            except Exception:
                if job.callback is not None:
                    job.callback(job.job_id, np.zeros((0, self.service.dims), dtype=np.float32))
            finally:
                self._queue.task_done()

    def shutdown(self) -> None:
        self._running = False
        for _ in self._threads:
            self._queue.put(None)
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
