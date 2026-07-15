"""Typed knob catalog across NEXUS layers 1–5 + AROP meta."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class KnobLayer(str, Enum):
    HAOE = "haoe"
    ASCR = "ascr"
    RTG = "rtg"
    ROUTER = "router"
    AQR = "aqr"
    MAKS = "maks"
    MEM = "mem"
    OKF = "okf"
    AROP = "arop"


@dataclass(frozen=True, slots=True)
class KnobSpec:
    name: str
    layer: KnobLayer
    value_type: str  # float|int|str|bool
    default: Any
    min_value: float | None = None
    max_value: float | None = None
    description: str = ""


KNOB_CATALOG: dict[str, KnobSpec] = {
    # L1 HAOE / inference
    "thread_count": KnobSpec("thread_count", KnobLayer.HAOE, "int", 8, 1, 256, "OpenMP/llama thread count"),
    "openmp_schedule": KnobSpec("openmp_schedule", KnobLayer.HAOE, "str", "static", description="OpenMP schedule"),
    "numa_placement": KnobSpec("numa_placement", KnobLayer.HAOE, "str", "local", description="NUMA bind policy"),
    "kv_layout": KnobSpec("kv_layout", KnobLayer.HAOE, "str", "default"),
    "sglang_batch": KnobSpec("sglang_batch", KnobLayer.HAOE, "int", 1, 1, 64),
    "llamacpp_ctx": KnobSpec("llamacpp_ctx", KnobLayer.HAOE, "int", 4096, 512, 131072),
    "prefill_decode_split": KnobSpec("prefill_decode_split", KnobLayer.HAOE, "str", "soft"),
    "speculative_mode": KnobSpec("speculative_mode", KnobLayer.HAOE, "str", "self"),
    # L2 ASCR
    "draft_model": KnobSpec("draft_model", KnobLayer.ASCR, "str", "tier1"),
    "verify_strategy": KnobSpec("verify_strategy", KnobLayer.ASCR, "str", "token"),
    "accept_threshold": KnobSpec("accept_threshold", KnobLayer.ASCR, "float", 0.7, 0.0, 1.0),
    "escalate_threshold": KnobSpec("escalate_threshold", KnobLayer.ASCR, "float", 0.4, 0.0, 1.0),
    "draft_len": KnobSpec("draft_len", KnobLayer.ASCR, "int", 8, 1, 64),
    "self_speculation": KnobSpec("self_speculation", KnobLayer.ASCR, "bool", True),
    "verify_batch": KnobSpec("verify_batch", KnobLayer.ASCR, "int", 1, 1, 16),
    "speculation_depth": KnobSpec("speculation_depth", KnobLayer.ASCR, "int", 1, 1, 4),
    # L3 orchestration
    "model_routing": KnobSpec("model_routing", KnobLayer.ROUTER, "str", "cascade"),
    "budget_usd": KnobSpec("budget_usd", KnobLayer.RTG, "float", 0.05, 0.0, 1.0),
    "router_top_k": KnobSpec("router_top_k", KnobLayer.ROUTER, "int", 3, 1, 20),
    "planning_depth": KnobSpec("planning_depth", KnobLayer.ROUTER, "int", 2, 1, 8),
    "reasoning_cap": KnobSpec("reasoning_cap", KnobLayer.RTG, "int", 512, 32, 8192),
    "agent_topology": KnobSpec("agent_topology", KnobLayer.ROUTER, "str", "default"),
    "mcp_routing_threshold": KnobSpec("mcp_routing_threshold", KnobLayer.ROUTER, "float", 0.5, 0.0, 1.0),
    # L4 memory
    "mem0_retention": KnobSpec("mem0_retention", KnobLayer.MEM, "float", 0.7, 0.0, 1.0),
    "okf_compression": KnobSpec("okf_compression", KnobLayer.OKF, "str", "summary"),
    "retrieval_depth": KnobSpec("retrieval_depth", KnobLayer.MEM, "int", 5, 1, 50),
    "context_budget": KnobSpec("context_budget", KnobLayer.MEM, "int", 1200, 100, 32000),
    "context_summarization": KnobSpec("context_summarization", KnobLayer.MEM, "bool", True),
    "semantic_cache": KnobSpec("semantic_cache", KnobLayer.MEM, "bool", True),
    "memory_eviction": KnobSpec("memory_eviction", KnobLayer.MEM, "str", "lru"),
    "replay_policy": KnobSpec("replay_policy", KnobLayer.MEM, "str", "fifo"),
    # MAKS L5
    "maks_eviction_weight": KnobSpec("maks_eviction_weight", KnobLayer.MAKS, "float", 1.0, 0.0, 10.0),
    "maks_prefetch": KnobSpec("maks_prefetch", KnobLayer.MAKS, "float", 0.5, 0.0, 1.0),
    "maks_tier_threshold": KnobSpec("maks_tier_threshold", KnobLayer.MAKS, "float", 0.7, 0.0, 1.0),
    # AQR
    "quant_preference": KnobSpec("quant_preference", KnobLayer.AQR, "str", "Q5_K_M"),
    # AROP meta
    "canary_percent": KnobSpec("canary_percent", KnobLayer.AROP, "float", 10.0, 0.0, 100.0),
    "experiment_sample_size": KnobSpec("experiment_sample_size", KnobLayer.AROP, "int", 30, 5, 1000),
}


def layers_for_parameters(parameters: dict[str, Any]) -> frozenset[str]:
    layers: set[str] = set()
    for key in parameters:
        spec = KNOB_CATALOG.get(key)
        if spec:
            layers.add(spec.layer.value)
    return frozenset(layers)


def clamp_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in parameters.items():
        spec = KNOB_CATALOG.get(key)
        if spec is None:
            out[key] = value
            continue
        if spec.value_type == "float":
            v = float(value)
            if spec.min_value is not None:
                v = max(spec.min_value, v)
            if spec.max_value is not None:
                v = min(spec.max_value, v)
            out[key] = v
        elif spec.value_type == "int":
            v = int(value)
            if spec.min_value is not None:
                v = max(int(spec.min_value), v)
            if spec.max_value is not None:
                v = min(int(spec.max_value), v)
            out[key] = v
        elif spec.value_type == "bool":
            out[key] = bool(value)
        else:
            out[key] = value
    return out
