"""Health checks for Cognitive Memory Runtime."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.memory.providers.base import IMemoryProvider
from neuroswarm_arm.runtime.memory.schemas import HealthStatus


class MemoryHealth:
    def __init__(self, provider: IMemoryProvider, *, secondary: IMemoryProvider | None = None) -> None:
        self.provider = provider
        self.secondary = secondary

    def check(self) -> HealthStatus:
        details: dict[str, Any] = {}
        try:
            primary = self.provider.health()
            details["primary"] = primary
            healthy = bool(primary.get("healthy", True))
        except Exception as exc:  # noqa: BLE001
            details["primary_error"] = str(exc)
            healthy = False
        if self.secondary is not None:
            try:
                details["secondary"] = self.secondary.health()
            except Exception as exc:  # noqa: BLE001
                details["secondary_error"] = str(exc)
        return HealthStatus(healthy=healthy, provider=getattr(self.provider, "name", "unknown"), details=details)
