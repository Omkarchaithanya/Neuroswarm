"""Continuous batching — enabled only when backend capability allows."""

from __future__ import annotations


class ContinuousBatcher:
    def __init__(self, enabled: bool = False, max_batch: int = 64) -> None:
        self.enabled = enabled
        self.max_batch = max_batch

    def can_coalesce(self, backend_supports: bool) -> bool:
        return self.enabled and backend_supports
