"""RMF schemas — metric definitions, samples, domains, export formats."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    NATIVE_HISTOGRAM = "native_histogram"
    INFO = "info"
    STATESET = "stateset"


class MetricDomain(str, Enum):
    REQUEST = "request"
    ADMISSION = "admission"
    PLANNER = "planner"
    ROUTING = "routing"
    HAOE = "haoe"
    DIPA = "dipa"
    BUDGET = "budget"
    RUNTIME_COST = "runtime_cost"
    MEMORY = "memory"
    HARDWARE = "hardware"
    PERFORMIX = "performix"
    ENERGY = "energy"
    RMF = "rmf"
    LEGACY = "legacy"


class ExportFormat(str, Enum):
    PROMETHEUS = "prometheus"
    OPENMETRICS = "openmetrics"
    OTLP = "otlp"


class MetricDef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    metric_type: MetricType
    help: str
    domain: MetricDomain
    label_keys: tuple[str, ...] = ()
    buckets: tuple[float, ...] = ()
    objectives: Mapping[float, float] = Field(default_factory=dict)
    unit: str = ""
    aliases: tuple[str, ...] = ()
    native_histogram: bool = False


class LabelSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    values: Mapping[str, str] = Field(default_factory=dict)

    def as_tuple(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((str(k), str(v)) for k, v in self.values.items()))


class Exemplar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float
    labels: Mapping[str, str] = Field(default_factory=dict)
    timestamp_ms: float | None = None


class MetricSample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: float
    metric_type: MetricType = MetricType.GAUGE
    labels: Mapping[str, str] = Field(default_factory=dict)
    exemplar: Exemplar | None = None
    help_text: str = ""


class MetricUpdateOp(str, Enum):
    INC = "inc"
    SET = "set"
    OBSERVE = "observe"
    INFO = "info"


class MetricUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    op: MetricUpdateOp
    value: float = 1.0
    labels: Mapping[str, str] = Field(default_factory=dict)
    exemplar: Exemplar | None = None


class SeriesSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    metric_type: MetricType
    help: str
    labels: Mapping[str, str] = Field(default_factory=dict)
    value: float
    bucket_counts: Mapping[str, float] = Field(default_factory=dict)
    sum: float = 0.0
    count: float = 0.0
    quantiles: Mapping[str, float] = Field(default_factory=dict)
    info: Mapping[str, str] = Field(default_factory=dict)
    exemplar: Exemplar | None = None


class RegistrySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    series: tuple[SeriesSnapshot, ...] = ()
    dropped_labels: int = 0
    cardinality_rejects: int = 0
    buffer_drops: int = 0


class AggregatedWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    avg: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    count: float = 0.0
    sum: float = 0.0
    labels: Mapping[str, str] = Field(default_factory=dict)
    extras: Mapping[str, Any] = Field(default_factory=dict)


DEFAULT_LATENCY_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)

DEFAULT_TOKEN_BUCKETS: tuple[float, ...] = (
    1.0,
    4.0,
    16.0,
    64.0,
    256.0,
    1024.0,
    4096.0,
    16384.0,
)

DEFAULT_JOULE_BUCKETS: tuple[float, ...] = (
    0.01,
    0.1,
    0.5,
    1.0,
    5.0,
    10.0,
    50.0,
    100.0,
    500.0,
)
