"""Performix ObservationProvider — CLI backend (MCP optional)."""

from __future__ import annotations

import json
import shutil
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
from neuroswarm_arm.evolution.performix_mcp_client import PerformixMCPClient


def _write_rmf_snapshot(metrics: dict[str, float], payload: dict[str, Any], out: Path) -> None:
    """Write Grafana/RMF snapshot with honest source=apx|unavailable (never silent demo)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    hotspots = payload.get("hotspots") or payload.get("parsed", {}).get("hotspots") or []
    if not isinstance(hotspots, list):
        hotspots = []
    avail = float(metrics.get("performix_available", 0) or 0) > 0
    payload_src = str(payload.get("source") or (payload.get("parsed") or {}).get("source") or "")
    err = (
        payload.get("error")
        or metrics.get("performix_error")
        or (None if avail else "apx_recipe_failed")
    )
    if avail and hotspots:
        source = "apx"
        available = 1.0
        error = None
    else:
        source = "unavailable"
        available = 0.0
        error = str(err) if err else "apx_unavailable"
        # Drop misleading payload source=demo if present
        if payload_src in {"demo", "synthetic"}:
            error = error or "stale_demo_cleared"

    body: dict[str, Any] = {
        "available": available,
        "source": source,
        "cycles": metrics.get("cycles", metrics.get("nexus_performix_cycles", 0.0)),
        "instructions": metrics.get("instructions", metrics.get("nexus_performix_instructions", 0.0)),
        "ipc": metrics.get("ipc", 0.0) if available else 0.0,
        "cache_misses": metrics.get("cache_misses", metrics.get("cache_miss_rate", 0.0)),
        "branch_misses": metrics.get("branch_misses", 0.0),
        "pmu_available": float(metrics.get("pmu_available", 1.0 if available else 0.0)),
        "hotspots": hotspots if available else [],
        "recommendations": payload.get("recommendations")
        or payload.get("parsed", {}).get("recommendations")
        or [],
        "metrics": metrics,
    }
    if error:
        body["error"] = error
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")


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
        snapshot_path: Path | None = None,
    ) -> None:
        self.client = client or PerformixClient()
        self.output_dir = output_dir or Path("work/arop/performix")
        self.recipe = recipe
        self.enabled = enabled
        self.binary_target = binary_target
        self.snapshot_path = snapshot_path or Path("work/performix/snapshot.json")
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
        if shutil.which(self.client.binary) is None:
            self._last = {"performix_available": 0.0, "performix_apx_missing": 1.0}
            _write_rmf_snapshot(self._last, {"error": "apx_missing"}, self.snapshot_path)
            return [
                RawObservation(
                    source=self.name,
                    collected_at=datetime.now(timezone.utc),
                    metrics=dict(self._last),
                    labels={"mode": "apx_missing"},
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
        try:
            data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
            if isinstance(data, dict):
                result = {**result, **data}
        except Exception:
            pass
        _write_rmf_snapshot(metrics, result, self.snapshot_path)
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
                    hotspots = data.get("hotspots") or []
                    if isinstance(hotspots, list) and hotspots:
                        top = hotspots[0]
                        if isinstance(top, dict) and "pct" in top:
                            metrics["hotspot_top_pct"] = float(top["pct"])
                        metrics["hotspot_count"] = float(len(hotspots))
            except Exception:
                pass
        return metrics


class PerformixMCPObservationProvider(ObservationProvider):
    """Arm Performix MCP ObservationProvider with CLI fallback."""

    name = "performix_mcp"

    def __init__(
        self,
        *,
        mcp_url: str = "",
        fallback: PerformixObservationProvider | None = None,
        snapshot_path: Path | None = None,
    ) -> None:
        self.mcp_url = mcp_url
        self.fallback = fallback or PerformixObservationProvider(enabled=False)
        self.snapshot_path = snapshot_path or Path("work/performix/snapshot.json")
        self._client = PerformixMCPClient(mcp_url=mcp_url) if mcp_url else None
        self._last: dict[str, float] = {}
        self._last_payload: dict[str, Any] = {}

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        if not self.mcp_url or self._client is None:
            return self.fallback.collect(window)

        recipe = getattr(self.fallback, "recipe", "code-hotspots")
        out_dir = getattr(self.fallback, "output_dir", Path("work/arop/performix"))
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{recipe}.json"
        duration = min(60, max(5, int((window.end - window.start).total_seconds())))

        try:
            tools = self._client.list_tools()
            if tools and "apx_recipe_run" not in tools and not any("recipe" in t for t in tools):
                # MCP up but no Performix tools — fall back to CLI
                obs = self.fallback.collect(window)
                self._last = {"performix_mcp_available": 1.0, "performix_mcp_no_recipe_tool": 1.0}
                self._last.update(self.fallback.metrics())
                return obs

            result = self._client.recipe_run(recipe, output=out, duration=duration)
            metrics = {
                "performix_mcp_available": 1.0 if result.get("ok", True) and not result.get("error") else 0.0,
                "performix_mcp_stub": 0.0,
            }
            if out.exists():
                metrics.update(self.fallback._parse_output(out, {"returncode": 0 if metrics["performix_mcp_available"] else 1}))
            parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else {}
            self._last = metrics
            self._last_payload = result
            _write_rmf_snapshot(metrics, {**result, **parsed}, self.snapshot_path)
            return [
                RawObservation(
                    source=self.name,
                    collected_at=datetime.now(timezone.utc),
                    metrics=metrics,
                    labels={"mcp_url": self.mcp_url, "mode": "mcp", "recipe": recipe},
                    payload=result,
                )
            ]
        except Exception as exc:
            obs = self.fallback.collect(window)
            self._last = {
                "performix_mcp_available": 0.0,
                "performix_mcp_error": 1.0,
                **self.fallback.metrics(),
            }
            self._last_payload = {"error": str(exc)}
            return obs

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
            details={
                "mcp_url": self.mcp_url or None,
                "mode": "mcp" if self.mcp_url else "fallback",
                "last": dict(self._last),
            },
        )
