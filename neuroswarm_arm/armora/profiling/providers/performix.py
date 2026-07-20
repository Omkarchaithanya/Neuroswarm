"""ARM Performix optional profiler provider — never a hard dependency."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..schemas import (
    CapabilityState,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)
from .base import (
    BaseProfilerProvider,
    empty_batch,
    samples_from_mapping,
    which_binary,
)

logger = logging.getLogger(__name__)


class PerformixProfilerProvider(BaseProfilerProvider):
    name = "performix"

    def __init__(
        self,
        *,
        binary: str = "apx",
        recipe: str = "code_hotspots",
        output_dir: Path | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__()
        self.binary_name = binary
        self.recipe = recipe
        self.output_dir = output_dir or Path("work/profiling/performix")
        self.enabled = enabled
        self._client: Any | None = None
        self._apx = which_binary(binary)
        self._recommendations: list[str] = []
        if self._apx and enabled:
            try:
                from neuroswarm_arm.evolution.performix_client import PerformixClient

                self._client = PerformixClient(binary=self._apx)
            except Exception as exc:
                self._mark_failure(exc)
                self._client = None

    def capabilities(self) -> ProviderCapabilities:
        ok = bool(self.enabled and self._apx and self._client is not None)
        reasons: list[str] = []
        if not self.enabled:
            reasons.append("performix disabled by config")
        if not self._apx:
            reasons.append(f"{self.binary_name} not on PATH")
        if self._client is None and self._apx:
            reasons.append("PerformixClient unavailable")
        return ProviderCapabilities(
            name=self.name,
            available=ok,
            state=CapabilityState.AVAILABLE if ok else CapabilityState.UNAVAILABLE,
            sampling=ok,
            tracing=False,
            cpu=ok,
            memory=ok,
            hardware=ok,
            continuous=False,
            reasons=tuple(reasons),
            extensions={"recipe": self.recipe},
        )

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        if not self.capabilities().available or self._client is None:
            return empty_batch(self.name, session)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            out = self.output_dir / f"{session.session_id}-{self.recipe}.json"
            result = self._client.run_recipe(
                self.recipe,
                output=out,
                duration=5,
            )
            values, recs = self._parse_output(out, result)
            self._recommendations = recs
            if not values:
                return empty_batch(self.name, session)
            return samples_from_mapping(self.name, session, values)
        except Exception as exc:
            self._mark_failure(exc)
            return empty_batch(self.name, session)

    def recommendations(self) -> list[str]:
        return list(self._recommendations)

    def _parse_output(
        self, path: Path, result: dict[str, Any]
    ) -> tuple[dict[str, float], list[str]]:
        values: dict[str, float] = {}
        recs: list[str] = []
        payload: dict[str, Any] = {}
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        if not payload and isinstance(result.get("stdout"), str):
            try:
                payload = json.loads(result["stdout"])
            except Exception:
                payload = {}
        # Flexible parse across Performix recipe shapes
        metrics = payload.get("metrics") if isinstance(payload, dict) else None
        if isinstance(metrics, dict):
            for k, v in metrics.items():
                try:
                    values[f"performix.{k}"] = float(v)
                except Exception:
                    continue
        hotspots = payload.get("hotspots") or payload.get("functions") or []
        if isinstance(hotspots, list) and hotspots:
            top = hotspots[0]
            if isinstance(top, dict):
                name = str(top.get("name") or top.get("function") or "unknown")
                pct = top.get("percent") or top.get("self") or top.get("samples") or 0
                try:
                    values["performix.top_hotspot_percent"] = float(pct)
                except Exception:
                    pass
                recs.append(f"Hotspot: {name} ({pct}%)")
        for key in ("cycles", "instructions", "ipc", "cache_misses", "branch_misses"):
            if key in payload:
                try:
                    values[f"hardware.{key}"] = float(payload[key])
                except Exception:
                    pass
        if result.get("returncode") not in (0, None):
            values["performix.available"] = 0.0
        else:
            values["performix.available"] = 1.0
        return values, recs
