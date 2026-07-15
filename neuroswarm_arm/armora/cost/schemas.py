"""Pydantic v2 schemas for Runtime Cost Intelligence System."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Objective(str, Enum):
    COST = "cost"
    LATENCY = "latency"
    ENERGY = "energy"
    QUALITY = "quality"
    PARETO = "pareto"


class WorkloadKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = "chat"
    model_tier: str = ""
    backend: str = ""
    quantization: str = ""
    agent_role: str = "default"


class HardwareMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    arch: str = ""
    cpu_model: str = ""
    numa_node: int = 0
    thread_count: int = 1
    platform: str = ""
    performix_available: bool = False
    pmu_available: bool = False
    extensions: dict[str, Any] = Field(default_factory=dict)


class TelemetryMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    otel_service: str = "nexus.armora.rcis"
    prometheus_job: str = "neuroswarm-rcis"
    exporter: str = "prometheus"
    extensions: dict[str, Any] = Field(default_factory=dict)


class LiveCostBreakdown(BaseModel):
    """Multi-resource optimization-signal cost — not an invoice."""

    # extra=ignore so round-trips that include computed total_runtime_cost still validate
    model_config = ConfigDict(extra="ignore", frozen=True)

    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    reasoning_cost: float = 0.0
    cpu_cost: float = 0.0
    memory_cost: float = 0.0
    energy_cost: float = 0.0
    kv_cost: float = 0.0
    tool_cost: float = 0.0
    retry_cost: float = 0.0
    streaming_cost: float = 0.0
    planner_cost: float = 0.0
    queue_cost: float = 0.0
    speculation_net: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_runtime_cost(self) -> float:
        return float(
            self.prompt_cost
            + self.completion_cost
            + self.reasoning_cost
            + self.cpu_cost
            + self.memory_cost
            + self.energy_cost
            + self.kv_cost
            + self.tool_cost
            + self.retry_cost
            + self.streaming_cost
            + self.planner_cost
            + self.queue_cost
            + self.speculation_net
        )


class CostPrediction(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    prediction_id: str = Field(default_factory=new_id)
    request_id: str = ""
    execution_id: str = ""
    expected_latency_ms: float = 0.0
    expected_cost_usd: float = 0.0
    expected_memory_bytes: float = 0.0
    expected_cpu_seconds: float = 0.0
    expected_energy_joules: float = 0.0
    expected_prompt_tokens: float = 0.0
    expected_completion_tokens: float = 0.0
    expected_reasoning_tokens: float = 0.0
    expected_kv_growth_bytes: float = 0.0
    confidence: float = 0.5
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    extensions: dict[str, Any] = Field(default_factory=dict)


class PredictionErrorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cost_error: float = 0.0
    latency_error: float = 0.0
    memory_error: float = 0.0
    energy_error: float = 0.0
    cpu_error: float = 0.0
    token_error: float = 0.0
    kv_error: float = 0.0
    planner_accuracy: float = 1.0
    relative_cost_error: float = 0.0
    relative_latency_error: float = 0.0


class ObservedRuntimeSignals(BaseModel):
    """Post-execution observations from DIPA/MAKS/AQR/ASCR/psutil/PMU."""

    model_config = ConfigDict(extra="allow")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    accepted_speculative_tokens: int = 0
    rejected_speculative_tokens: int = 0
    kv_cache_hits: int = 0
    kv_cache_misses: int = 0
    kv_memory_bytes: float = 0.0
    pages_shared: int = 0
    migration_events: int = 0
    compression_savings_bytes: float = 0.0
    cpu_seconds: float = 0.0
    wall_time_ms: float = 0.0
    planner_time_ms: float = 0.0
    queue_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    streaming_time_ms: float = 0.0
    peak_memory_bytes: float = 0.0
    average_memory_bytes: float = 0.0
    energy_joules: float = 0.0
    watts_estimate: float = 0.0
    tool_calls: int = 0
    retry_count: int = 0
    quality_score: float = 1.0
    success: bool = True
    failure_reason: str = ""
    verifier_overhead_ms: float = 0.0
    draft_model_cost_usd: float = 0.0
    verifier_cost_usd: float = 0.0
    avg_cpu_utilization: float = 0.0
    extensions: dict[str, Any] = Field(default_factory=dict)


class RequestContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str = Field(default_factory=new_id)
    execution_id: str = Field(default_factory=new_id)
    workflow_id: str = ""
    user_id: str = ""
    agent_id: str = ""
    planner_id: str = ""
    envelope_id: str = ""
    tenant_id: str = ""
    model: str = ""
    model_tier: str = ""
    backend: str = ""
    quantization: str = ""
    slo_latency_ms: float = 4000.0
    prompt_token_estimate: int = 0
    planner_decision_trace: dict[str, Any] = Field(default_factory=dict)
    hardware: HardwareMetadata = Field(default_factory=HardwareMetadata)
    telemetry: TelemetryMetadata = Field(default_factory=TelemetryMetadata)
    trace_ids: dict[str, str] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class RuntimeCostReport(BaseModel):
    """Immutable per-inference learning signal for ARMORA / planner feedback."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: str = "1.0.0"
    report_id: str = Field(default_factory=new_id)

    request_id: str = ""
    execution_id: str = ""
    workflow_id: str = ""
    user_id: str = ""
    agent_id: str = ""
    planner_id: str = ""
    envelope_id: str = ""
    tenant_id: str = ""

    model: str = ""
    model_tier: str = ""
    backend: str = ""
    quantization: str = ""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    accepted_speculative_tokens: int = 0
    rejected_speculative_tokens: int = 0

    kv_cache_hits: int = 0
    kv_cache_misses: int = 0
    kv_reuse_ratio: float = 0.0
    kv_memory_bytes: float = 0.0
    pages_shared: int = 0
    migration_events: int = 0
    compression_savings_bytes: float = 0.0
    memory_saved_bytes: float = 0.0

    cpu_seconds: float = 0.0
    wall_time_ms: float = 0.0
    planner_time_ms: float = 0.0
    queue_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    streaming_time_ms: float = 0.0
    latency_ms: float = 0.0
    slo_latency_ms: float = 4000.0

    peak_memory_bytes: float = 0.0
    average_memory_bytes: float = 0.0

    energy_estimate_joules: float = 0.0
    watts_estimate: float = 0.0
    estimated_dollars: float = 0.0
    estimated_carbon_kg: float = 0.0
    cost_breakdown: LiveCostBreakdown = Field(default_factory=LiveCostBreakdown)

    throughput_tokens_per_s: float = 0.0
    tokens_per_watt: float = 0.0
    tokens_per_dollar: float = 0.0

    quality_score: float = 1.0
    success: bool = True
    failure_reason: str = ""
    retry_count: int = 0

    speculation_acceptance_ratio: float = 0.0
    verifier_overhead_ms: float = 0.0
    draft_model_cost_usd: float = 0.0
    verifier_cost_usd: float = 0.0
    speculation_net_savings_usd: float = 0.0

    planner_decision_trace: dict[str, Any] = Field(default_factory=dict)
    prediction: CostPrediction | None = None
    prediction_errors: PredictionErrorReport | None = None

    hardware_metadata: HardwareMetadata = Field(default_factory=HardwareMetadata)
    telemetry_metadata: TelemetryMetadata = Field(default_factory=TelemetryMetadata)
    trace_ids: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    extensions: dict[str, Any] = Field(default_factory=dict)


class RankedChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    score: float
    samples: int = 0
    mean_cost: float = 0.0
    mean_latency_ms: float = 0.0
    mean_energy_joules: float = 0.0
    mean_quality: float = 0.0
    confidence: float = 0.0


class RankedChoices(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: Objective
    choices: list[RankedChoice] = Field(default_factory=list)
    window: int = 0


class UnitEconomics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_per_prompt_token: float = 0.0
    cost_per_completion_token: float = 0.0
    cost_per_reasoning_token: float = 0.0
    cost_per_useful_token: float = 0.0
    cost_per_accepted_draft_token: float = 0.0
    cost_per_tool_call: float = 0.0
    cost_per_cpu_second: float = 0.0
    cost_per_joule: float = 0.0
    cost_per_request: float = 0.0
    cost_per_backend: dict[str, float] = Field(default_factory=dict)
    cost_per_quantization: dict[str, float] = Field(default_factory=dict)
    cost_per_model_tier: dict[str, float] = Field(default_factory=dict)
    cost_per_workflow: dict[str, float] = Field(default_factory=dict)
    cost_per_agent: dict[str, float] = Field(default_factory=dict)
    cost_per_conversation: dict[str, float] = Field(default_factory=dict)


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den == 0.0:
        return default
    return float(num) / float(den)


def as_mapping(model: BaseModel) -> Mapping[str, Any]:
    return model.model_dump(mode="json")
