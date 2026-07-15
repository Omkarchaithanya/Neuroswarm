"""ConfigurationManager — typed access to DIPA runtime config + env overlays."""

from __future__ import annotations

import os
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.runtime.runtime_config import DIPARuntimeConfig


class ConfigurationManager:
    def __init__(self, config: DIPARuntimeConfig) -> None:
        self.config = config

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self.config, key, default)

    def require_kleidiai(self) -> bool:
        return os.getenv("NSA_REQUIRE_KLEIDIAI", "0").strip() in {"1", "true", "TRUE", "yes"}

    def queue_maxsize(self) -> int:
        return int(os.getenv("NSA_DIPA_QUEUE_MAX", "1024"))

    def scheduler_workers(self) -> int:
        return int(os.getenv("NSA_DIPA_SCHED_WORKERS", "4"))

    def otel_enabled(self) -> bool:
        return bool(self.config.otel_enabled)

    def otel_endpoint(self) -> str:
        return str(self.config.otel_endpoint or "")

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "otel_enabled": self.otel_enabled(),
            "otel_endpoint": self.otel_endpoint(),
            "require_kleidiai": self.require_kleidiai(),
            "queue_maxsize": self.queue_maxsize(),
            "scheduler_workers": self.scheduler_workers(),
            "max_retries": self.config.max_retries,
            "default_timeout_s": self.config.default_timeout_s,
            "cascade_confidence": self.config.cascade_confidence,
        }
