"""Prometheus text exporter — sole prometheus_client boundary (optional mirror)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..schemas import MetricType

if TYPE_CHECKING:
    from ..registry import MetricRegistry

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class PrometheusExporter:
    """Render registry snapshot as Prometheus exposition format 0.0.4."""

    def __init__(self, registry: MetricRegistry, **_kwargs: object) -> None:
        self.registry = registry
        self._prom_registry = None
        try:
            from prometheus_client import CollectorRegistry

            self._prom_registry = CollectorRegistry(auto_describe=False)
        except Exception:
            self._prom_registry = None

    def content_type(self) -> str:
        return CONTENT_TYPE

    def export(self) -> str:
        snap = self.registry.snapshot()
        lines: list[str] = []
        seen: set[str] = set()
        for item in sorted(snap.series, key=lambda s: (s.name, tuple(sorted(s.labels.items())))):
            if item.name not in seen:
                if item.help:
                    lines.append(f"# HELP {item.name} {item.help}")
                type_name = item.metric_type.value
                if item.metric_type == MetricType.NATIVE_HISTOGRAM:
                    type_name = "histogram"
                if item.metric_type == MetricType.INFO:
                    type_name = "gauge"
                lines.append(f"# TYPE {item.name} {type_name}")
                seen.add(item.name)
            label_str = _fmt_labels(item.labels)
            if item.metric_type in (MetricType.HISTOGRAM, MetricType.NATIVE_HISTOGRAM):
                for bound, count in item.bucket_counts.items():
                    bl = dict(item.labels)
                    bl["le"] = bound
                    lines.append(f"{item.name}_bucket{_fmt_labels(bl)} {count}")
                inf = dict(item.labels)
                inf["le"] = "+Inf"
                lines.append(f"{item.name}_bucket{_fmt_labels(inf)} {item.count}")
                lines.append(f"{item.name}_sum{label_str} {item.sum}")
                lines.append(f"{item.name}_count{label_str} {item.count}")
            elif item.metric_type == MetricType.SUMMARY:
                for q, val in item.quantiles.items():
                    ql = dict(item.labels)
                    ql["quantile"] = q
                    lines.append(f"{item.name}{_fmt_labels(ql)} {val}")
                lines.append(f"{item.name}_sum{label_str} {item.sum}")
                lines.append(f"{item.name}_count{label_str} {item.count}")
            elif item.metric_type == MetricType.INFO:
                lines.append(f"{item.name}{_fmt_labels(item.info or item.labels)} 1")
            else:
                lines.append(f"{item.name}{label_str} {item.value}")
        return "\n".join(lines) + ("\n" if lines else "")


def _fmt_labels(labels: dict[str, str] | object) -> str:
    if not labels:
        return ""
    mapping = dict(labels)  # type: ignore[arg-type]
    parts = [f'{k}="{v}"' for k, v in sorted(mapping.items())]
    return "{" + ",".join(parts) + "}"
