"""Runtime Metrics Framework (RMF) — NEXUS-ARM metrics operating system.

Prometheus / OpenMetrics / OTLP are exporters only. Subsystems publish via the
registry / MetricPublisher and never construct prometheus_client objects.
"""

from __future__ import annotations

from .aggregators import WindowAggregator
from .alerts import default_alert_groups, render_alert_yaml, write_alert_rules
from .buffer import AsyncMetricBuffer
from .collectors import PerformixCollector, PsutilCollector
from .compat import MetricsStore, build_default_store
from .config import RMFRuntimeConfig, load_rmf_config
from .dashboards import default_dashboards, write_dashboards
from .labels import ALLOWED_LABELS, FORBIDDEN_LABELS, LabelPolicy
from .bridges import PlaneMetricBridge, RMFObservationProvider
from .lifecycle import RuntimeMetricsFramework, build_rmf, get_registry, get_rmf, peek_rmf
from .metrics import (
    CounterHandle,
    GaugeHandle,
    HistogramHandle,
    InfoHandle,
    MetricPublisher,
    NativeHistogramHandle,
    SummaryHandle,
)
from .middleware import RMFMiddleware, install_rmf_middleware
from .plugins import (
    discover_plugins,
    plugin_registry,
    register_aggregator,
    register_alert_rules,
    register_collector,
    register_dashboard,
    register_exporter,
    register_provider,
)
from .recording_rules import default_recording_groups, render_recording_yaml, write_recording_rules
from .registry import MetricRegistry
from .schemas import (
    Exemplar,
    ExportFormat,
    MetricDef,
    MetricDomain,
    MetricSample,
    MetricType,
    RegistrySnapshot,
)

# Global legacy bridge — bound to RMF on first use / build_rmf
metrics = build_default_store()

__all__ = [
    "ALLOWED_LABELS",
    "FORBIDDEN_LABELS",
    "AsyncMetricBuffer",
    "CounterHandle",
    "Exemplar",
    "ExportFormat",
    "GaugeHandle",
    "HistogramHandle",
    "InfoHandle",
    "LabelPolicy",
    "MetricDef",
    "MetricDomain",
    "MetricPublisher",
    "MetricRegistry",
    "MetricSample",
    "MetricType",
    "MetricsStore",
    "NativeHistogramHandle",
    "PerformixCollector",
    "PlaneMetricBridge",
    "PsutilCollector",
    "RMFMiddleware",
    "RMFObservationProvider",
    "RMFRuntimeConfig",
    "RegistrySnapshot",
    "RuntimeMetricsFramework",
    "SummaryHandle",
    "WindowAggregator",
    "build_default_store",
    "build_rmf",
    "default_alert_groups",
    "default_dashboards",
    "default_recording_groups",
    "discover_plugins",
    "get_registry",
    "get_rmf",
    "install_rmf_middleware",
    "load_rmf_config",
    "metrics",
    "peek_rmf",
    "plugin_registry",
    "register_aggregator",
    "register_alert_rules",
    "register_collector",
    "register_dashboard",
    "register_exporter",
    "register_provider",
    "render_alert_yaml",
    "render_recording_yaml",
    "write_alert_rules",
    "write_dashboards",
    "write_recording_rules",
]
