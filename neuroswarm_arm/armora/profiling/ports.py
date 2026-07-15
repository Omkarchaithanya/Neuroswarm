"""Ports / Protocols for hexagonal Runtime Profiling Framework."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .schemas import (
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
    ProviderHealth,
    RankedChoices,
    RuntimeProfile,
)


@runtime_checkable
class IProfilerProvider(Protocol):
    @property
    def name(self) -> str: ...

    def capabilities(self) -> ProviderCapabilities: ...

    def initialize(self) -> None: ...

    def start(self, session: ProfileSessionContext) -> None: ...

    def sample(self, session: ProfileSessionContext) -> MetricBatch: ...

    def stop(self, session: ProfileSessionContext) -> MetricBatch: ...

    def shutdown(self) -> None: ...

    def health(self) -> ProviderHealth: ...


@runtime_checkable
class ISamplingProfiler(Protocol):
    def sample(self, session: ProfileSessionContext) -> MetricBatch: ...


@runtime_checkable
class ITracingProfiler(Protocol):
    def start_span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> str: ...

    def end_span(self, span_id: str) -> None: ...


@runtime_checkable
class ICPUProfiler(Protocol):
    def cpu_sample(self, session: ProfileSessionContext) -> MetricBatch: ...


@runtime_checkable
class IMemoryProfiler(Protocol):
    def memory_sample(self, session: ProfileSessionContext) -> MetricBatch: ...


@runtime_checkable
class IHardwareProfiler(Protocol):
    def hardware_sample(self, session: ProfileSessionContext) -> MetricBatch: ...


@runtime_checkable
class IMetricsCollector(Protocol):
    def collect(self, session: ProfileSessionContext) -> MetricBatch: ...


@runtime_checkable
class IProfileCollector(Protocol):
    def open_session(self, **kwargs: Any) -> ProfileSessionContext: ...

    def record_phase(self, session_id: str, **timings: Any) -> None: ...

    def sample(self, session_id: str) -> MetricBatch: ...

    def finalize(self, session_id: str) -> RuntimeProfile: ...


@runtime_checkable
class IProfileExporter(Protocol):
    def name(self) -> str: ...

    def export(self, profile: RuntimeProfile) -> None: ...


@runtime_checkable
class IProfilerFeedback(Protocol):
    async def hottest_backends(self, *, limit: int = 10) -> RankedChoices: ...

    async def worst_ipc_workloads(self, *, limit: int = 10) -> RankedChoices: ...

    async def latency_percentiles(self, *, backend: str = "") -> RankedChoices: ...


@runtime_checkable
class IPhaseSignalSource(Protocol):
    def push_phase(self, session_id: str, **timings: Any) -> None: ...


@runtime_checkable
class IProfileTelemetry(Protocol):
    def record_profile(self, profile: RuntimeProfile) -> None: ...

    def record_failure(self, provider: str, reason: str) -> None: ...

    def export_prometheus(self) -> str: ...

    def snapshot(self) -> Mapping[str, Any]: ...
