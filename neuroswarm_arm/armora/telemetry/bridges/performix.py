"""ARM Performix metric source + optional profile spans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas import MetricSample, SpanNames


class PerformixMetricSource:
    """Read Performix / PMU snapshot JSON into Prometheus gauges."""

    name = "performix"

    def __init__(self, snapshot_path: str | Path = "work/haoe/performix_snapshot.json") -> None:
        self.snapshot_path = Path(snapshot_path)

    def _load(self) -> dict[str, Any]:
        if not self.snapshot_path.exists():
            return {}
        try:
            return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def collect(self) -> list[MetricSample]:
        data = self._load()
        samples: list[MetricSample] = []
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else data
        if not isinstance(metrics, dict):
            return samples
        for key, value in metrics.items():
            try:
                samples.append(
                    MetricSample(
                        name=f"nexus_performix_{key}",
                        value=float(value),
                        metric_type="gauge",
                        labels={"subsystem": "performix"},
                        help_text=f"Performix metric {key}",
                    )
                )
            except (TypeError, ValueError):
                continue
        return samples

    def export_prometheus(self) -> str:
        lines: list[str] = []
        for sample in self.collect():
            lines.append(f"# TYPE {sample.name} gauge")
            lines.append(f"{sample.name} {sample.value}")
        return "\n".join(lines) + ("\n" if lines else "")

    def profile_span(self, rof: Any, recipe: str = "system-characterization"):
        return rof.span(SpanNames.PERFORMIX, attributes={"nexus.performix.recipe": recipe})
