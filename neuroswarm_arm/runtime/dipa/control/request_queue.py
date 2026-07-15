"""RequestQueue — bounded async-safe admission queue."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QueuedRequest:
    request_id: str
    payload: Any
    enqueued_at: float = field(default_factory=time.time)
    priority: int = 0


class RequestQueue:
    def __init__(self, maxsize: int = 1024) -> None:
        self.maxsize = max(1, maxsize)
        self._lock = threading.Lock()
        self._q: deque[QueuedRequest] = deque()
        self._cond = threading.Condition(self._lock)
        self._closed = False
        self._enqueued = 0
        self._dequeued = 0
        self._rejected = 0

    def enqueue(self, payload: Any, *, priority: int = 0) -> QueuedRequest:
        with self._cond:
            if self._closed:
                raise RuntimeError("request queue closed")
            if len(self._q) >= self.maxsize:
                self._rejected += 1
                raise RuntimeError("request queue full")
            item = QueuedRequest(
                request_id=f"req_{uuid.uuid4().hex[:12]}",
                payload=payload,
                priority=priority,
            )
            if priority > 0:
                # Higher priority closer to left (front).
                inserted = False
                for i, existing in enumerate(self._q):
                    if priority > existing.priority:
                        self._q.insert(i, item)
                        inserted = True
                        break
                if not inserted:
                    self._q.append(item)
            else:
                self._q.append(item)
            self._enqueued += 1
            self._cond.notify()
            return item

    def dequeue(self, timeout_s: float | None = None) -> QueuedRequest | None:
        deadline = None if timeout_s is None else time.time() + timeout_s
        with self._cond:
            while not self._q and not self._closed:
                if deadline is None:
                    self._cond.wait()
                else:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    self._cond.wait(timeout=remaining)
            if not self._q:
                return None
            item = self._q.popleft()
            self._dequeued += 1
            return item

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def depth(self) -> int:
        with self._lock:
            return len(self._q)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "depth": len(self._q),
                "maxsize": self.maxsize,
                "enqueued": self._enqueued,
                "dequeued": self._dequeued,
                "rejected": self._rejected,
                "closed": self._closed,
            }
