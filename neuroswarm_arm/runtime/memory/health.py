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
        provider_name = getattr(self.provider, "name", "unknown")
        mode = "primary"
        emergency_active = False
        try:
            primary = self.provider.health()
            details["primary"] = primary
            healthy = bool(primary.get("healthy", True))
            # Mem0Adapter may report mode=emergency_json while still named mem0
            if str(primary.get("mode", "")).lower() in {"emergency_json", "json_emergency"}:
                emergency_active = True
                mode = "emergency_json"
            if str(primary.get("provider", "")).lower() in {"json_emergency", "json", "fallback"}:
                emergency_active = True
                mode = "emergency_json"
                provider_name = str(primary.get("provider") or provider_name)
            if provider_name in {"json_emergency", "json", "fallback"}:
                emergency_active = True
                mode = "emergency_json"
        except Exception as exc:  # noqa: BLE001
            details["primary_error"] = str(exc)
            healthy = False
            if self.secondary is not None:
                emergency_active = True
                mode = "emergency_json"
                provider_name = getattr(self.secondary, "name", "json_emergency")
        if self.secondary is not None:
            try:
                details["secondary"] = self.secondary.health()
            except Exception as exc:  # noqa: BLE001
                details["secondary_error"] = str(exc)
        details["provider"] = provider_name
        details["mode"] = mode
        details["emergency_active"] = emergency_active
        return HealthStatus(healthy=healthy, provider=provider_name, details=details)
