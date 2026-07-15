"""AQR Pydantic models — RequestContext, InferencePlan, Candidate, scores."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArmoraHints(BaseModel):
    """Budget/policy/priority hints from ARMORA (proxy not required)."""

    budget_usd: float | None = None
    policy: str | None = None
    priority: float | None = None


class HardwareCapabilities(BaseModel):
    arch: str = "unknown"
    cpu_cores: int = 1
    available_ram_bytes: int = 0
    l3_cache_bytes: int = 0
    memory_bandwidth_gbps: float = 0.0
    numa_nodes: int = 1
    openmp_threads: int = 1
    cpu_load: float = 0.0
    thermal_throttling: bool = False
    sve2: str = "UNKNOWN"
    i8mm: str = "UNKNOWN"
    dotprod: str = "UNKNOWN"
    bf16: str = "UNKNOWN"
    kleidiai: str = "UNKNOWN"
    hugepages: str = "UNKNOWN"
    thp: str = "UNKNOWN"
    mte: str = "UNAVAILABLE"
    cxl: str = "UNAVAILABLE"
    details: dict[str, Any] = Field(default_factory=dict)


class BackendStatus(BaseModel):
    name: str
    available: bool = False
    healthy: bool = False
    supported_quants: list[str] = Field(default_factory=list)
    supported_models: list[str] = Field(default_factory=list)
    throughput_tps: float = 0.0
    queue_length: int = 0
    latency_ms: float = 0.0
    warm: bool = False
    batching: bool = False
    streaming: bool = True
    speculative_decode: bool = False
    kv_sharing: bool = False
    numa_aware: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ModelEntry(BaseModel):
    name: str
    path: str = ""
    version: str = ""
    quant: str = ""
    size_bytes: int = 0
    size_b: float = 0.0
    ram_requirement_bytes: int = 0
    kv_size_estimate_bytes: int = 0
    supported_backends: list[str] = Field(default_factory=lambda: ["llama_cpp"])
    context_length: int = 4096
    instruction_tuned: bool = True
    embedding_support: bool = False
    vision_support: bool = False
    tool_calling_support: bool = True
    reasoning_capability: float = 0.5
    license: str = "unknown"
    preferred_hardware: list[str] = Field(default_factory=lambda: ["arm", "cpu"])
    tier: int = 0
    warm: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuantProfile(BaseModel):
    name: str
    bits: float
    quality: float
    latency: float
    memory: float
    expected_perplexity: float = 5.0
    arm_kernel: bool = False
    kleidiai: bool = False
    llama_cpp: bool = True
    vllm: bool = False
    executorch: bool = False
    litert: bool = False
    supported: bool = True
    workloads: list[str] = Field(default_factory=list)


class FeatureVector(BaseModel):
    """Frozen schema for Phase-1 heuristics and future RL."""

    reasoning_score: float = 0.0
    tool_likelihood: float = 0.0
    memory_score: float = 0.0
    cost_score: float = 0.0
    quality_score: float = 0.0
    latency_score: float = 0.0
    expected_compute_intensity: float = 0.0
    cache_locality_score: float = 0.0
    backend_suitability_score: float = 0.0
    quantization_suitability_score: float = 0.0
    warm_bonus: float = 0.0
    governor_accuracy_demand: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return self.model_dump()

    def as_list(self) -> list[float]:
        return list(self.as_dict().values())


class CandidateScores(BaseModel):
    overall: float = 0.0
    quality: float = 0.0
    latency: float = 0.0
    memory: float = 0.0
    cost: float = 0.0
    energy: float = 0.0
    availability: float = 0.0
    risk: float = 0.0
    confidence: float = 0.0


class RuntimeCandidate(BaseModel):
    model: str
    quant: str
    backend: str
    model_path: str = ""
    endpoint: str = ""
    size_b: float = 1.0
    cost_per_1k: float = 0.001
    warm: bool = False
    scores: CandidateScores = Field(default_factory=CandidateScores)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeFlags(BaseModel):
    threads: int = 4
    batch_size: int = 1
    numa_node: int = 0
    hugepages: bool = False
    kleidiai: bool = False
    sve2: bool = False
    dotprod: bool = False
    i8mm: bool = False
    bf16: bool = False
    thread_affinity: list[int] = Field(default_factory=list)
    openmp_threads: int = 4
    launch_args: dict[str, Any] = Field(default_factory=dict)


class DispatchPlan(BaseModel):
    primary: str = ""
    fallbacks: list[str] = Field(default_factory=list)
    cascade_start_tier: int = 1
    use_cascade: bool = True
    speculative_decode: bool = False
    kv_cache_policy: str = "reuse_if_compatible"
    governor_settings: dict[str, Any] = Field(default_factory=dict)


class CascadeTierPlan(BaseModel):
    tiers: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RequestContext(BaseModel):
    """Rich context for AQR planning."""

    user_request: str = ""
    task_type: str = "chat"
    agent_role: str = "tool_call"
    planner_stage: str = ""
    conversation_length: int = 0
    reasoning_depth: float = 0.0
    latency_sla_ms: float = 4000.0
    budget_usd: float = 0.01
    current_cost_usd: float = 0.0
    memory_pressure: float = 0.0
    kv_cache_pressure: float = 0.0
    token_length: int = 0
    prompt_length: int = 0
    expected_output_tokens: int = 256
    temperature: float = 0.2
    top_k: int | None = None
    top_p: float | None = None
    streaming: bool = False
    speculative_decode_enabled: bool = False
    cascade_tier: int = 1
    awpp_prediction: str | None = None
    armora: ArmoraHints = Field(default_factory=ArmoraHints)
    haoe_scheduling_priority: float = 0.5
    dipa_execution_plan: dict[str, Any] = Field(default_factory=dict)
    shared_kv_available: bool = False
    model_warm_state: dict[str, bool] = Field(default_factory=dict)
    hardware: HardwareCapabilities = Field(default_factory=HardwareCapabilities)
    backends: list[BackendStatus] = Field(default_factory=list)
    loaded_models: list[str] = Field(default_factory=list)
    queue_length: int = 0
    worker_load: float = 0.0
    workload: str = "tool_calling"
    intent: str = ""
    session_id: str = ""
    agent_id: str = "default"
    governor_accuracy_demand: float = 0.0
    thinking_token_cap: int | None = None
    baggage: dict[str, Any] = Field(default_factory=dict)


class InferencePlan(BaseModel):
    """AQR output — HOW to run inference."""

    model: str = "tier2"
    quant: str = "Q5_K_M"
    backend: str = "llama_cpp"
    model_path: str = ""
    endpoint: str = ""
    runtime_flags: RuntimeFlags = Field(default_factory=RuntimeFlags)
    dispatch: DispatchPlan = Field(default_factory=DispatchPlan)
    cascade: CascadeTierPlan = Field(default_factory=CascadeTierPlan)
    scores: CandidateScores = Field(default_factory=CandidateScores)
    features: FeatureVector = Field(default_factory=FeatureVector)
    candidate_count: int = 0
    decision_latency_ms: float = 0.0
    confidence: float = 0.0
    risk: float = 0.0
    estimated_cost_usd: float = 0.0
    estimated_ttft_ms: float = 0.0
    estimated_e2e_ms: float = 0.0
    estimated_ram_bytes: int = 0
    top_candidates: list[RuntimeCandidate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_execution_overlay(self) -> dict[str, Any]:
        """Fields to merge onto DIPA ExecutionPlan."""
        return {
            "model": self.model,
            "quant": self.quant,
            "backend": self.backend,
            "numa_node": self.runtime_flags.numa_node,
            "affinity_cores": list(self.runtime_flags.thread_affinity),
            "use_cascade": self.dispatch.use_cascade,
            "cascade_start_tier": self.dispatch.cascade_start_tier,
            "speculation": self.dispatch.speculative_decode,
            "fallbacks": list(self.dispatch.fallbacks),
            "scores": {
                "aqr_overall": self.scores.overall,
                "aqr_quality": self.scores.quality,
                "aqr_latency": self.scores.latency,
                "aqr_memory": self.scores.memory,
                "aqr_cost": self.scores.cost,
            },
            "metadata": {
                "aqr": {
                    "model_path": self.model_path,
                    "endpoint": self.endpoint,
                    "runtime_flags": self.runtime_flags.model_dump(),
                    "cascade": self.cascade.model_dump(),
                    "dispatch": self.dispatch.model_dump(),
                    "decision_latency_ms": self.decision_latency_ms,
                    "candidate_count": self.candidate_count,
                    "confidence": self.confidence,
                    "risk": self.risk,
                    "estimated_cost_usd": self.estimated_cost_usd,
                    "estimated_ttft_ms": self.estimated_ttft_ms,
                    "estimated_e2e_ms": self.estimated_e2e_ms,
                    "estimated_ram_bytes": self.estimated_ram_bytes,
                    "features": self.features.model_dump(),
                }
            },
        }
