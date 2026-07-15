"""OpenMetrics 1.0 text exporter with optional exemplars."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..schemas import MetricType

if TYPE_CHECKING:
    from ..registry import MetricRegistry

CONTENT_TYPE = "application/openmetrics-text; version=1.0.0; charset=utf-8"


class OpenMetricsExporter:
    def __init__(self, registry: MetricRegistry, **_kwargs: object) -> None:
        self.registry = registry

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
                    type_name = "info"
                lines.append(f"# TYPE {item.name} {type_name}")
                seen.add(item.name)
            label_str = _fmt_labels(item.labels)
            if item.metric_type in (MetricType.HISTOGRAM, MetricType.NATIVE_HISTOGRAM):
                for bound, count in item.bucket_counts.items():
                    bl = dict(item.labels)
                    bl["le"] = bound
                    line = f"{item.name}_bucket{_fmt_labels(bl)} {count}"
                    if item.exemplar is not None:
                        line += _fmt_exemplar(item.exemplar.labels, item.exemplar.value)
                    lines.append(line)
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
            elif item.metric_type == MetricType.COUNTER:
                lines.append(f"{item.name}{label_str} {item.value}")
            else:
                lines.append(f"{item.name}{label_str} {item.value}")
        lines.append("# EOF")
        return "\n".join(lines) + "\n"


def _fmt_labels(labels: dict[str, str] | object) -> str:
    if not labels:
        return ""
    mapping = dict(labels)  # type: ignore[arg-type]
    parts = [f'{k}="{v}"' for k, v in sorted(mapping.items())]
    return "{" + ",".join(parts) + "}"


def _fmt_exemplar(labels: object, value: float) -> str:
    mapping = dict(labels) if labels else {}  # type: ignore[arg-type]
    if not mapping:
        return f" # {{}} {value}"
    parts = [f'{k}="{v}"' for k, v in sorted(mapping.items())]
    return " # {" + ",".join(parts) + f"}} {value}"
