"""Batch manager facade."""

from __future__ import annotations

from typing import Any

from .continuous_batching import ContinuousBatcher
from .dynamic_batching import DynamicBatcher
from .micro_batching import MicroBatcher


class BatchManager:
    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        cfg = cfg or {}
        micro = cfg.get("micro", {})
        dyn = cfg.get("dynamic", {})
        cont = cfg.get("continuous", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.micro = MicroBatcher(
            max_batch=int(micro.get("max_batch", 8)),
            window_ms=float(micro.get("window_ms", 10)),
        )
        self.dynamic = DynamicBatcher(
            target_latency_ms=float(dyn.get("target_latency_ms", 50)),
            max_batch=int(dyn.get("max_batch", 32)),
        )
        self.continuous = ContinuousBatcher(
            enabled=bool(cont.get("enabled", False)),
            max_batch=int(cont.get("max_batch", 64)),
        )

    def offer_micro(self, item: Any) -> list[Any] | None:
        if not self.enabled:
            return [item]
        return self.micro.offer(item)
