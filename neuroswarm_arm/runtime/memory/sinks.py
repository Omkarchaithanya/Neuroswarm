"""Optional sinks — push cost/perf samples into NeuroMemory without tight coupling."""

from __future__ import annotations

from typing import Any


def remember_armora_cost(memory: Any, *, owner: str, cost_usd: float, label: str = "armora") -> None:
    neuro = memory if hasattr(memory, "remember_cost") else getattr(memory, "neuro", None)
    if neuro is None:
        return
    try:
        neuro.remember_cost(
            f"{label} cost_usd={cost_usd}",
            owner=owner or "default",
            cost=float(cost_usd),
            tags=["armora", "cost"],
        )
    except Exception:
        pass


def remember_dipa_performance(
    memory: Any,
    *,
    owner: str,
    latency_ms: float = 0.0,
    ttft_ms: float = 0.0,
    tokens_per_sec: float = 0.0,
) -> None:
    neuro = memory if hasattr(memory, "remember_performance") else getattr(memory, "neuro", None)
    if neuro is None:
        return
    runtime = getattr(neuro, "runtime", None)
    if runtime is not None and hasattr(runtime, "should_sample_performance"):
        if not runtime.should_sample_performance():
            return
    try:
        neuro.remember_performance(
            f"dipa latency_ms={latency_ms} ttft_ms={ttft_ms} tok_s={tokens_per_sec}",
            owner=owner or "default",
            latency=latency_ms,
            metadata={"ttft_ms": ttft_ms, "tokens_per_sec": tokens_per_sec},
            tags=["dipa", "performance"],
        )
        if latency_ms > 0:
            neuro.remember_latency(
                f"dipa latency_ms={latency_ms}",
                owner=owner or "default",
                latency=latency_ms,
                tags=["dipa", "latency"],
            )
    except Exception:
        pass
