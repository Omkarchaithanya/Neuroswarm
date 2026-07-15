"""BatchScheduler — facade over BatchManager; does not reimplement continuous batching."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class BatchScheduler:
    """Admit / size batches when backend capabilities.continuous_batching is True."""

    def __init__(self, batch_manager: Any | None = None) -> None:
        self.batch_manager = batch_manager
        self._last_size = 1

    def recommend_size(
        self,
        *,
        pending: int,
        continuous_batching: bool,
        max_batch: int = 32,
    ) -> int:
        if not continuous_batching or pending <= 1:
            self._last_size = 1
            return 1
        if self.batch_manager is not None:
            suggest = getattr(self.batch_manager, "suggest_batch_size", None)
            if callable(suggest):
                size = int(suggest(pending=pending, max_batch=max_batch) or 1)
                self._last_size = max(1, min(size, max_batch))
                return self._last_size
        self._last_size = max(1, min(pending, max_batch))
        return self._last_size

    def record(self, size: int) -> None:
        self._last_size = max(1, int(size))

    def snapshot(self) -> Mapping[str, Any]:
        return {"last_batch_size": float(self._last_size)}
