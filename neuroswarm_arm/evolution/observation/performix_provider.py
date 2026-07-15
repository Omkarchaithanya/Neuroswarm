"""Performix ObservationProvider — CLI backend (MCP optional)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neuroswarm_arm.evolution.interfaces.observation import ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)
from neuroswarm_arm.evolution.performix_client import PerformixClient


class PerformixObservationProvider(ObservationProvider):
    name = "performix"

    def __init__(
        self,
        client: PerformixClient | None = None,
        *,
        output_dir: Path | None = None,
        recipe: str = "code-hotspots",
        enabled: bool = False,
        binary_target: str | None = None,
    ) -> None:
        self.client = client or PerformixClient()
        self.output_dir = output_dir or Path("work/arop/performix")
        self.recipe = recipe
        self.enabled = enabled
        self.binary_target = binary_target
        self._last: dict[str, float] = {}
        self._last_payload: dict[str, Any] = {}

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        if not self.enabled:
            return [
                RawObservation(
                    source=self.name,
                    collected_at=datetime.now(timezone.utc),
                    metrics=dict(self._last) or {"performix_available": 0.0},
                    labels={"mode": "disabled"},
                )
            ]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out = self.output_dir / f"{self.recipe}.json"
        result = self.client.run_recipe(
            self.recipe,
            output=out,
            binary=self.binary_target,
            duration=min(60, max(5, int((window.end - window.start).total_seconds()))),
        )
        metrics = self._parse_output(out, result)
        self._last = metrics
        self._last_payload = result
        return [
            RawObservation(
                source=self.name,
                collected_at=datetime.now(timezone.utc),
                metrics=metrics,
                labels={"recipe": self.recipe},
                payload=result,
            )
        ]

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: dict(self._last)},
            aggregate=dict(self._last),
        )

    def metrics(self) -> dict[str, float]:
        return dict(self._last)

    def health(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            provider=self.name,
            details={"enabled": self.enabled, "recipe": self.recipe, "last": dict(self._last)},
        )

    def _parse_output(self, path: Path, result: dict[str, Any]) -> dict[str, float]:
        metrics: dict[str, float] = {
            "performix_returncode": float(result.get("returncode", 1)),
            "performix_available": 1.0 if result.get("returncode") == 0 else 0.0,
        }
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key in ("cpu_util", "energy_joules", "hotspot_pct", "ipc", "cache_miss_rate"):
                        if key in data:
                            metrics[key] = float(data[key])
                    summary = data.get("summary") or data.get("metrics") or {}
                    if isinstance(summary, dict):
                        for k, v in summary.items():
                            try:
                                metrics[str(k)] = float(v)
                            except (TypeError, ValueError):
                                continue
            except Exception:
                pass
        return metrics


class PerformixMCPObservationProvider(ObservationProvider):
    """Arm Performix MCP ObservationProvider (optional; falls back to CLI)."""

    name = "performix_mcp"

    def __init__(
        self,
        *,
        mcp_url: str = "",
        fallback: PerformixObservationProvider | None = None,
    ) -> None:
        self.mcp_url = mcp_url
        self.fallback = fallback or PerformixObservationProvider(enabled=False)
        self._last: dict[str, float] = {}

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        if not self.mcp_url:
            return self.fallback.collect(window)
        # MCP client is optional; degrade gracefully for CI/Axion without Arm MCP.
        try:
            from mcp import ClientSession  # type: ignore  # noqa: F401

            # Real MCP wiring requires a running Arm MCP server; keep interface ready.
            self._last = {"performix_mcp_available": 0.0, "performix_mcp_stub": 1.0}
        except Exception:
            return self.fallback.collect(window)
        return [
            RawObservation(
                source=self.name,
                collected_at=datetime.now(timezone.utc),
                metrics=dict(self._last),
                labels={"mcp_url": self.mcp_url, "mode": "stub"},
            )
        ]

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: dict(self._last)},
            aggregate=dict(self._last),
        )

    def metrics(self) -> dict[str, float]:
        return dict(self._last) or self.fallback.metrics()

    def health(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            provider=self.name,
            details={"mcp_url": self.mcp_url or None, "mode": "stub_or_fallback"},
        )
