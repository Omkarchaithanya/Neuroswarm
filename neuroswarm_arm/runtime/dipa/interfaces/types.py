"""DIPA shared types — enums, request/plan envelopes, scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Mapping, Sequence

from neuroswarm_arm.runtime.router.models import RoutingResult


class FeatureStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class WorkloadClass(str, Enum):
    REASONING = "reasoning"
    CODING = "coding"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    TOOL_CALLING = "tool_calling"
    VISION = "vision"
    SPEECH = "speech"
    CLASSIFICATION = "classification"


class DeviceClass(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    NPU = "npu"
    CXL = "cxl"
    SME = "sme"


class ExecutionPhase(str, Enum):
    ADMITTED = "admitted"
    PLANNED = "planned"
    CLASSIFIED = "classified"
    INTENT_DETECTED = "intent_detected"
    MODEL_SELECTED = "model_selected"
    BACKEND_SELECTED = "backend_selected"
    HARDWARE_PROBED = "hardware_probed"
    POLICY_APPLIED = "policy_applied"
    QUANT_RESOLVED = "quant_resolved"
    WARM_CHECKED = "warm_checked"
    KV_ATTACHED = "kv_attached"
    CASCADE = "cascade"
    PREFILL = "prefill"
    DECODE = "decode"
    STREAMING = "streaming"
    METRICS = "metrics"
    RECOVERING = "recovering"
    DEGRADED = "degraded"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QuantLevel(str, Enum):
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    Q4_0 = "Q4_0"
    Q4_K_M = "Q4_K_M"
    Q5 = "Q5"
    Q5_K_M = "Q5_K_M"
    Q6 = "Q6"
    Q8_0 = "Q8_0"
    INT8 = "INT8"
    FP16 = "FP16"
    BF16 = "BF16"
    FP8 = "FP8"
    MXFP = "MXFP"


class PoolKind(str, Enum):
    PREFILL = "prefill"
    DECODE = "decode"
    BATCH = "batch"
    STREAM = "stream"
    WARM = "warm"
    BACKGROUND = "background"


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class KVTransferMode(str, Enum):
    """Honest KV handoff modes (ADR-0006)."""

    NATIVE_SGLANG = "native_sglang"
    RECOMPUTE = "recompute"
    UNAVAILABLE = "unavailable"


class PDMode(str, Enum):
    OFF = "off"
    SOFT = "soft"
    NATIVE = "native"


@dataclass(slots=True)
class BackendCapabilities:
    streaming: bool = True
    batching: bool = False
    continuous_batching: bool = False
    prefill_decode_split: bool = False
    prefix_caching: bool = False
    chunked_prefill: bool = False
    radix_attention: bool = False
    tokenize: bool = False
    vision: bool = False
    speech: bool = False
    embedding: bool = False
    speculation: bool = False
    self_speculation: bool = False
    kleidiai: bool = False
    kv_transfer_modes: tuple[KVTransferMode, ...] = ()
    device_classes: tuple[DeviceClass, ...] = (DeviceClass.CPU,)


@dataclass(slots=True)
class HealthStatus:
    state: HealthState = HealthState.UNKNOWN
    latency_ms: float = 0.0
    utilization: float = 0.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CorrelationIds:
    request_id: str = ""
    agent_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    execution_id: str = ""
    correlation_id: str = ""


@dataclass(slots=True)
class InferenceRequest:
    """Normalized inference request entering DIPA."""

    messages: list[dict[str, str]]
    model: str = "cascade"
    max_tokens: int = 1024
    temperature: float = 0.2
    agent_role: str = "tool_call"
    session_id: str = ""
    agent_id: str = "default"
    stream: bool = False
    tool_names: list[str] = field(default_factory=list)
    tool_schemas: list[dict[str, Any]] = field(default_factory=list)
    tool_confidence: float = 0.0
    tool_high_confidence: bool = False
    tool_prompt_block: str = ""
    thinking_token_cap: int | None = None
    system_prompt: str | None = None
    latency_sla_ms: float = 4000.0
    cost_budget_usd: float = 0.01
    baggage: dict[str, Any] = field(default_factory=dict)
    ids: CorrelationIds = field(default_factory=CorrelationIds)
    # Typed Any at the field to avoid tightening router imports for all DIPA callers;
    # DecisionEngine / cascade coerce to RoutingResult at the use site when present.
    router_result: Any | None = None

    @property
    def prompt_text(self) -> str:
        if not self.messages:
            return ""
        return str(self.messages[-1].get("content", ""))

    @property
    def prompt_length(self) -> int:
        return len(self.prompt_text.split())


@dataclass(slots=True)
class TokenChunk:
    text: str
    token_id: int | None = None
    index: int = 0
    finished: bool = False
    channel: str = "answer"  # "thinking" | "answer"
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ReasoningEvent:
    """Ordered reasoning-trace envelope for SSE ``reason.*`` events."""

    kind: str
    data: dict[str, Any]
    ts_ms: float


@dataclass(slots=True)
class PrefillRequest:
    messages: list[dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.2
    session_id: str = ""
    quant: str = "Q5_K_M"
    kv_handle: str | None = None
    chunk_id: int = 0
    chunk_total: int = 1
    transfer_mode: KVTransferMode = KVTransferMode.RECOMPUTE


@dataclass(slots=True)
class PrefillResult:
    prefix_tokens: int = 0
    kv_handle: str | None = None
    latency_ms: float = 0.0
    backend: str = ""
    prefix_hit_tokens: int = 0
    chunk_id: int = 0
    transfer_mode: KVTransferMode = KVTransferMode.RECOMPUTE
    radix_node_id: str = ""
    bootstrap_room: str = ""
    token_ids: list[int] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class DecodeRequest:
    messages: list[dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.2
    session_id: str = ""
    quant: str = "Q5_K_M"
    kv_handle: str | None = None
    stream: bool = True
    transfer_mode: KVTransferMode = KVTransferMode.RECOMPUTE
    bootstrap_room: str = ""
    radix_node_id: str = ""
    prefix_hit_tokens: int = 0
    recompute_tokens: int = 0
    token_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class GenerateRequest:
    messages: list[dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.2
    session_id: str = ""
    quant: str = "Q5_K_M"
    stream: bool = False
    kv_handle: str | None = None
    id_slot: int | None = None
    speculative: bool = False
    cache_prompt_tokens: list[int] = field(default_factory=list)
    baggage: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GenerateResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    ttft_ms: float = 0.0
    backend: str = ""
    model: str = ""
    quant: str = ""
    tier_used: int = 1
    raw: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ModelCandidate:
    name: str
    size_b: float
    roles: tuple[str, ...] = ()
    latency_hint_ms: float = 100.0
    cost_per_1k: float = 0.001
    reasoning: bool = False


@dataclass(slots=True)
class RouteScore:
    name: str
    score: float
    factors: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionPlan:
    """Planner output — full decision envelope for one request."""

    workload: WorkloadClass = WorkloadClass.TOOL_CALLING
    intent: str = ""
    model: str = "tier2"
    backend: str = "llama_cpp"
    quant: str = "Q5_K_M"
    device_class: DeviceClass = DeviceClass.CPU
    use_cascade: bool = True
    cascade_start_tier: int = 1
    speculation: bool = False
    self_speculation: bool = False
    stream: bool = False
    pd_enabled: bool = False
    pd_mode: PDMode = PDMode.OFF
    prefill_backend: str = ""
    decode_backend: str = ""
    transfer_mode: KVTransferMode = KVTransferMode.RECOMPUTE
    prefill_pool: PoolKind = PoolKind.PREFILL
    decode_pool: PoolKind = PoolKind.DECODE
    affinity_cores: list[int] = field(default_factory=list)
    prefill_cores: list[int] = field(default_factory=list)
    decode_cores: list[int] = field(default_factory=list)
    numa_node: int = 0
    latency_sla_ms: float = 4000.0
    cost_budget_usd: float = 0.01
    fallbacks: list[str] = field(default_factory=list)
    graph_nodes: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    router_result: RoutingResult | None = None


@dataclass(slots=True)
class InferenceResponse:
    text: str
    model: str = ""
    tier_used: int = 1
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_token_cap: int = 0
    tool_schemas_used: list[str] = field(default_factory=list)
    quant: str = ""
    backend: str = ""
    plan: ExecutionPlan | None = None
    metrics: dict[str, float | str] = field(default_factory=dict)
    degraded: bool = False


@dataclass(slots=True)
class BackendDescriptor:
    name: str
    kind: str
    endpoint: str = ""
    model_alias: str = ""
    tier: int = 0
    priority: float = 1.0
    capabilities: BackendCapabilities = field(default_factory=BackendCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)
