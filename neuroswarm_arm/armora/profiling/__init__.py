"""ARMORA Runtime Profiling Framework (RPF).

Profiling is an observation plane — never admit/enforce (Budget) and never cost-learn (RCIS).
ARM Performix is one optional IProfilerProvider; runtime never depends on it directly.
"""

from __future__ import annotations

from .arop_provider import ProfilingObservationProvider
from .collector import ProfileCollector
from .config import RPFRuntimeConfig, load_rpf_config
from .connectors import (
    PhaseSignalConnector,
    ProfileSignalBus,
    map_profile_to_runtime_signals,
)
from .exporters import (
    DuckDBProfileExporter,
    JsonProfileExporter,
    OTLPProfileExporter,
    ParquetProfileExporter,
    ProfileStore,
    SqliteProfileExporter,
    build_exporter,
)
from .feedback import ProfilerFeedbackService
from .lifecycle import LifecyclePhase, ProfilingLifecycle
from .plugins import (
    RPFPluginRegistry,
    register_dashboard,
    register_exporter,
    register_metric_source,
    register_profiler,
    register_report_builder,
    register_telemetry,
)
from .profiler import RuntimeProfilingFramework, build_rpf, build_rpf_at
from .providers import (
    EbpfProfilerProvider,
    MockProfilerProvider,
    ParcaProfilerProvider,
    PerfProfilerProvider,
    PerformixProfilerProvider,
    PsutilProfilerProvider,
    PyroscopeProfilerProvider,
)
from .registry import FailureIsolatingProxy, ProfilerRegistry
from .reports import ProfileReportBuilder
from .schemas import (
    BackendMetrics,
    CPUMetrics,
    CapabilityState,
    ExecutionMetrics,
    HardwareMetrics,
    MemoryMetrics,
    MetricBatch,
    MetricSample,
    NUMAMetrics,
    PhaseTimings,
    PlannerMetrics,
    ProfileSessionContext,
    ProfilingMode,
    ProviderCapabilities,
    ProviderHealth,
    RankedChoice,
    RankedChoices,
    RuntimeProfile,
    TelemetryMetadata,
)
from .telemetry import InMemoryProfileTelemetry, OpenTelemetryProfileBridge
from .traces import TraceRecorder

__all__ = [
    "BackendMetrics",
    "CPUMetrics",
    "CapabilityState",
    "DuckDBProfileExporter",
    "EbpfProfilerProvider",
    "ExecutionMetrics",
    "FailureIsolatingProxy",
    "HardwareMetrics",
    "InMemoryProfileTelemetry",
    "JsonProfileExporter",
    "LifecyclePhase",
    "MemoryMetrics",
    "MetricBatch",
    "MetricSample",
    "MockProfilerProvider",
    "NUMAMetrics",
    "OTLPProfileExporter",
    "OpenTelemetryProfileBridge",
    "ParcaProfilerProvider",
    "ParquetProfileExporter",
    "PerfProfilerProvider",
    "PerformixProfilerProvider",
    "PhaseSignalConnector",
    "PhaseTimings",
    "PlannerMetrics",
    "ProfileCollector",
    "ProfileReportBuilder",
    "ProfileSessionContext",
    "ProfileSignalBus",
    "ProfileStore",
    "ProfilerFeedbackService",
    "ProfilerRegistry",
    "ProfilingLifecycle",
    "ProfilingMode",
    "ProfilingObservationProvider",
    "ProviderCapabilities",
    "ProviderHealth",
    "PsutilProfilerProvider",
    "PyroscopeProfilerProvider",
    "RPFPluginRegistry",
    "RPFRuntimeConfig",
    "RankedChoice",
    "RankedChoices",
    "RuntimeProfile",
    "RuntimeProfilingFramework",
    "SqliteProfileExporter",
    "TelemetryMetadata",
    "TraceRecorder",
    "build_exporter",
    "build_rpf",
    "build_rpf_at",
    "load_rpf_config",
    "map_profile_to_runtime_signals",
    "register_dashboard",
    "register_exporter",
    "register_metric_source",
    "register_profiler",
    "register_report_builder",
    "register_telemetry",
]
