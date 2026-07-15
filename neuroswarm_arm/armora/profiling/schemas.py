"""Pydantic v2 schemas for Runtime Profiling Framework."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class ProfilingMode(str, Enum):
    DISABLED = "disabled"
    SAMPLING = "sampling"
    TRACING = "tracing"
    CONTINUOUS = "continuous"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    BENCHMARK = "benchmark"
    PRODUCTION = "production"
    DEBUG = "debug"


class CapabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    DEGRADED = "DEGRADED"


class RankedChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    score: float
    samples: int = 0
    labels: dict[str, str] = Field(default_factory=dict)


class RankedChoices(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    choices: list[RankedChoice] = Field(default_factory=list)
    objective: str = ""


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    name: str
    available: bool = False
    state: CapabilityState = CapabilityState.UNAVAILABLE
    sampling: bool = False
    tracing: bool = False
    cpu: bool = False
    memory: bool = False
    hardware: bool = False
    continuous: bool = False
    reasons: tuple[str, ...] = ()
    extensions: dict[str, Any] = Field(default_factory=dict)


class CPUMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    usage_percent: float = 0.0
    cpu_time_seconds: float = 0.0
    user_time_seconds: float = 0.0
    system_time_seconds: float = 0.0
    wall_time_ms: float = 0.0
    core_utilization: float = 0.0
    frequency_mhz: float = 0.0
    thread_count: int = 0
    context_switches: int = 0
    affinity: list[int] = Field(default_factory=list)


class MemoryMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    rss_bytes: float = 0.0
    vms_bytes: float = 0.0
    peak_rss_bytes: float = 0.0
    average_rss_bytes: float = 0.0
    percent: float = 0.0


class NUMAMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    node: int = 0
    nodes_available: int = 1
    local_hit_ratio: float = 1.0


class HardwareMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    cycles: float = 0.0
    instructions: float = 0.0
    ipc: float = 0.0
    cache_misses: float = 0.0
    cache_references: float = 0.0
    branch_misses: float = 0.0
    branch_instructions: float = 0.0
    llc_loads: float = 0.0
    llc_misses: float = 0.0
    sve2_available: bool = False
    i8mm_available: bool = False
    pmu_available: bool = False
    extensions: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def derived_ipc(self) -> float:
        if self.ipc > 0:
            return float(self.ipc)
        if self.cycles <= 0:
            return 0.0
        return float(self.instructions) / float(self.cycles)


class BackendMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    backend: str = ""
    model: str = ""
    model_tier: str = ""
    quantization: str = ""
    backend_time_ms: float = 0.0
    model_loading_time_ms: float = 0.0


class PlannerMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    planner_time_ms: float = 0.0
    routing_time_ms: float = 0.0
    queue_time_ms: float = 0.0


class ExecutionMetrics(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    execution_time_ms: float = 0.0
    streaming_time_ms: float = 0.0
    tool_execution_time_ms: float = 0.0
    kv_memory_bytes: float = 0.0
    accepted_speculative_tokens: int = 0
    rejected_speculative_tokens: int = 0
    speculative_acceptance_ratio: float = 0.0


class TelemetryMetadata(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    otel_service: str = "nexus.armora.rpf"
    prometheus_job: str = "neuroswarm-rpf"
    exporter: str = "prometheus"
    trace_ids: dict[str, str] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class MetricSample(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    name: str
    value: float
    unit: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: utcnow().isoformat())


class MetricBatch(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    samples: list[MetricSample] = Field(default_factory=list)
    provider: str = ""
    session_id: str = ""


class PhaseTimings(BaseModel):
    model_config = ConfigDict(extra="allow")

    planner_ms: float = 0.0
    routing_ms: float = 0.0
    execution_ms: float = 0.0
    streaming_ms: float = 0.0
    backend_ms: float = 0.0
    model_load_ms: float = 0.0
    tool_ms: float = 0.0
    queue_ms: float = 0.0
    kv_memory_bytes: float = 0.0
    accepted_speculative_tokens: int = 0
    rejected_speculative_tokens: int = 0
    backend: str = ""
    model: str = ""
    model_tier: str = ""
    quantization: str = ""
    extensions: dict[str, Any] = Field(default_factory=dict)


class ProfileSessionContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str = Field(default_factory=new_id)
    request_id: str = ""
    execution_id: str = Field(default_factory=new_id)
    workflow_id: str = ""
    agent_id: str = ""
    envelope_id: str = ""
    tenant_id: str = ""
    mode: ProfilingMode = ProfilingMode.PRODUCTION
    sampling_hz: float = 1.0
    started_at: str = Field(default_factory=lambda: utcnow().isoformat())
    extensions: dict[str, Any] = Field(default_factory=dict)


class RuntimeProfile(BaseModel):
    """Immutable per-request runtime profile — never mutates inference path."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: str = "1.0.0"
    profile_id: str = Field(default_factory=new_id)
    request_id: str = ""
    execution_id: str = ""
    workflow_id: str = ""
    agent_id: str = ""
    envelope_id: str = ""
    tenant_id: str = ""
    profiler_used: str = "mock"
    sampling_frequency_hz: float = 1.0
    mode: ProfilingMode = ProfilingMode.PRODUCTION
    cpu: CPUMetrics = Field(default_factory=CPUMetrics)
    memory: MemoryMetrics = Field(default_factory=MemoryMetrics)
    numa: NUMAMetrics = Field(default_factory=NUMAMetrics)
    hardware: HardwareMetrics = Field(default_factory=HardwareMetrics)
    backend: BackendMetrics = Field(default_factory=BackendMetrics)
    planner: PlannerMetrics = Field(default_factory=PlannerMetrics)
    execution: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    telemetry: TelemetryMetadata = Field(default_factory=TelemetryMetadata)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    extensions: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    name: str
    healthy: bool = True
    message: str = ""
    failures: int = 0
