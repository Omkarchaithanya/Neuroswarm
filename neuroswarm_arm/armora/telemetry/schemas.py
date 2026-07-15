"""ROF schemas — immutable telemetry records and semantic constants."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SpanNames:
    """Stable span name ABI: nexus.<subsystem>.<operation>."""

    REQUEST = "nexus.armora.request"
    ADMISSION = "nexus.armora.admission"
    POLICY = "nexus.armora.policy"
    BUDGET = "nexus.armora.budget"
    PLANNER = "nexus.dipa.planner"
    ROUTING = "nexus.dipa.routing"
    HAOE_WORKFLOW = "nexus.haoe.workflow"
    HAOE_TASK = "nexus.haoe.task"
    DIPA_INFER = "nexus.dipa.infer"
    BACKEND = "nexus.dipa.backend"
    STREAMING = "nexus.dipa.streaming"
    QUANT = "nexus.aqr.quant"
    WARM = "nexus.awpp.warm"
    KV = "nexus.maks.kv"
    SPEC = "nexus.ascr.spec"
    COST = "nexus.armora.rcis"
    EXPORT = "nexus.rof.export"
    TOOL = "nexus.router.tool"
    MEMORY = "nexus.acr.memory"
    PERFORMIX = "nexus.performix.sample"


class AttributeKeys:
    """Semantic attribute / baggage keys for NEXUS-ARM."""

    TRACE_ID = "nexus.trace_id"
    SPAN_ID = "nexus.span_id"
    REQUEST_ID = "nexus.request_id"
    EXECUTION_ID = "nexus.execution_id"
    WORKFLOW_ID = "nexus.workflow_id"
    AGENT_ID = "nexus.agent_id"
    CONVERSATION_ID = "nexus.conversation_id"
    PLANNER_ID = "nexus.planner_id"
    DECISION_ID = "nexus.decision_id"
    ENVELOPE_ID = "nexus.envelope_id"
    BUDGET_ID = "nexus.budget_id"
    BACKEND_ID = "nexus.backend_id"
    MODEL_ID = "nexus.model_id"
    QUANTIZATION = "nexus.quantization"
    WORKER_ID = "nexus.worker_id"
    THREAD_ID = "nexus.thread_id"
    NUMA_NODE = "nexus.numa_node"
    HARDWARE_ID = "nexus.hardware_id"
    COST_ESTIMATE = "nexus.cost_estimate"
    BUDGET_REMAINING = "nexus.budget_remaining"
    LATENCY_MS = "nexus.latency_ms"
    OUTCOME = "nexus.outcome"
    ERROR = "nexus.error"
    FORCE_SAMPLE = "nexus.force_sample"


class EventType(str, Enum):
    ADMISSION_STARTED = "AdmissionStarted"
    ADMISSION_FINISHED = "AdmissionFinished"
    PLANNER_STARTED = "PlannerStarted"
    PLANNER_COMPLETED = "PlannerCompleted"
    ROUTING_STARTED = "RoutingStarted"
    ROUTING_COMPLETED = "RoutingCompleted"
    INFERENCE_STARTED = "InferenceStarted"
    INFERENCE_FINISHED = "InferenceFinished"
    STREAMING_STARTED = "StreamingStarted"
    STREAMING_FINISHED = "StreamingFinished"
    BUDGET_EXCEEDED = "BudgetExceeded"
    BACKEND_FAILURE = "BackendFailure"
    RETRY_STARTED = "RetryStarted"
    RETRY_FINISHED = "RetryFinished"
    PROFILER_STARTED = "ProfilerStarted"
    PROFILER_FINISHED = "ProfilerFinished"
    COST_REPORT_GENERATED = "CostReportGenerated"
    PLANNER_LEARNED = "PlannerLearned"
    CUSTOM = "Custom"


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RuntimeEvent(BaseModel):
    """Typed runtime event envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    event_type: str
    timestamp: datetime = Field(default_factory=_utcnow)
    severity: EventSeverity = EventSeverity.INFO
    context: Mapping[str, Any] = Field(default_factory=dict)
    payload: Mapping[str, Any] = Field(default_factory=dict)


class SpanRecord(BaseModel):
    """Normalized span record for local exporters (JSON/SQLite/DuckDB)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    span_id: str
    trace_id: str
    parent_span_id: str = ""
    name: str
    start_ns: int
    end_ns: int = 0
    status: str = "unset"
    attributes: Mapping[str, Any] = Field(default_factory=dict)
    events: tuple[str, ...] = ()


class MetricSample(BaseModel):
    """Single metric observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: float
    metric_type: str = "gauge"
    labels: Mapping[str, str] = Field(default_factory=dict)
    help_text: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)


class LogRecord(BaseModel):
    """Structured JSON log record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime = Field(default_factory=_utcnow)
    level: str = "INFO"
    message: str
    logger: str = "nexus.rof"
    context: Mapping[str, Any] = Field(default_factory=dict)
    extra: Mapping[str, Any] = Field(default_factory=dict)


class SamplingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sampled: bool
    reason: str = ""
    force: bool = False


# Bounded label keys allowed on Prometheus metrics (cardinality guard)
ALLOWED_METRIC_LABELS: frozenset[str] = frozenset(
    {
        "tenant",
        "agent",
        "workflow",
        "tier",
        "backend",
        "model",
        "quant",
        "outcome",
        "exporter",
        "pool",
        "numa",
        "dim",
        "hardness",
        "action",
        "result",
        "scope",
        "planner_id",
        "model_tier",
        "subsystem",
    }
)

FORBIDDEN_METRIC_LABELS: frozenset[str] = frozenset(
    {
        "request_id",
        "trace_id",
        "span_id",
        "execution_id",
        "conversation_id",
        "envelope_id",
    }
)
