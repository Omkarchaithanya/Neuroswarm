"""Shared fixtures for RMRE tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import (
    ExecutionSnapshot,
    HealthState,
    ModelProfile,
    ModelTier,
    ResiliencePolicy,
    RuntimeSignals,
    WorkloadHint,
    build_resilience_engine,
    default_policy,
)


def make_catalog() -> dict[str, ModelProfile]:
    profiles = [
        ModelProfile(
            model_id="Qwen3-8B",
            family="qwen",
            tier=ModelTier.TIER1,
            context_length=32768,
            parameter_count=8.0,
            quantizations=["Q5_K_M", "Q4_K_M", "Q3_K_M"],
            supported_backends=["llama_cpp", "sglang"],
            estimated_latency=120.0,
            estimated_cost=0.002,
            estimated_memory=6.0,
            estimated_tokens_per_second=40.0,
            preferred_workloads=[WorkloadHint.CHAT, WorkloadHint.CODE],
            health=HealthState.HEALTHY,
            availability=1.0,
            priority=1.0,
        ),
        ModelProfile(
            model_id="Qwen3-3B",
            family="qwen",
            tier=ModelTier.TIER2,
            context_length=16384,
            parameter_count=3.0,
            quantizations=["Q5_K_M", "Q4_K_M", "Q3_K_M"],
            supported_backends=["llama_cpp", "sglang"],
            estimated_latency=80.0,
            estimated_cost=0.001,
            estimated_memory=3.0,
            estimated_tokens_per_second=70.0,
            preferred_workloads=[WorkloadHint.CHAT, WorkloadHint.TOOL_CALLING],
            health=HealthState.HEALTHY,
            availability=1.0,
            priority=0.85,
        ),
        ModelProfile(
            model_id="Phi-4-Mini",
            family="phi",
            tier=ModelTier.TIER3,
            context_length=8192,
            parameter_count=3.8,
            quantizations=["Q5_K_M", "Q4_K_M"],
            supported_backends=["llama_cpp"],
            estimated_latency=70.0,
            estimated_cost=0.0008,
            estimated_memory=2.5,
            estimated_tokens_per_second=90.0,
            preferred_workloads=[WorkloadHint.GENERAL],
            health=HealthState.HEALTHY,
            availability=1.0,
            priority=0.7,
        ),
        ModelProfile(
            model_id="Gemma",
            family="gemma",
            tier=ModelTier.TIER3,
            context_length=8192,
            parameter_count=2.0,
            quantizations=["Q4_K_M", "Q3_K_M"],
            supported_backends=["llama_cpp"],
            estimated_latency=60.0,
            estimated_cost=0.0005,
            estimated_memory=2.0,
            estimated_tokens_per_second=100.0,
            preferred_workloads=[WorkloadHint.CHAT],
            health=HealthState.HEALTHY,
            availability=1.0,
            priority=0.55,
        ),
        ModelProfile(
            model_id="TinyLlama",
            family="llama",
            tier=ModelTier.TIER4,
            context_length=2048,
            parameter_count=1.1,
            quantizations=["Q4_K_M", "Q3_K_M"],
            supported_backends=["llama_cpp"],
            estimated_latency=40.0,
            estimated_cost=0.0002,
            estimated_memory=1.0,
            estimated_tokens_per_second=150.0,
            preferred_workloads=[WorkloadHint.GENERAL],
            health=HealthState.HEALTHY,
            availability=1.0,
            priority=0.3,
        ),
    ]
    return {p.model_id: p for p in profiles}


def make_plan(**overrides) -> ExecutionSnapshot:
    data = {
        "execution_id": "ex_test",
        "request_id": "req_test",
        "model": "Qwen3-8B",
        "backend": "llama_cpp",
        "quant": "Q5_K_M",
        "context_length": 8192,
        "thread_count": 8,
        "reasoning_budget": 512,
        "tools_enabled": True,
    }
    data.update(overrides)
    return ExecutionSnapshot(**data)


def make_signals(**overrides) -> RuntimeSignals:
    data = {
        "execution_id": "ex_test",
        "model_available": True,
        "backend_available": True,
        "memory_pressure": 0.1,
        "queue_depth": 1.0,
        "latency_p99_ms": 200.0,
        "budget_remaining_ratio": 1.0,
        "budget_remaining_usd": 0.05,
        "thread_available": 8,
        "historical_failures": 0,
        "context_tokens_needed": 1024,
        "latency_slo_ms": 4000.0,
        "max_memory_gb": 16.0,
    }
    data.update(overrides)
    return RuntimeSignals(**data)


def fresh_engine(**kwargs):
    catalog = kwargs.pop("catalog", make_catalog())
    policies = kwargs.pop("policies", [default_policy()])
    return build_resilience_engine(catalog=catalog, policies=policies, **kwargs)


def make_policy(**overrides) -> ResiliencePolicy:
    base = default_policy().model_dump()
    base.update(overrides)
    return ResiliencePolicy.model_validate(base)
