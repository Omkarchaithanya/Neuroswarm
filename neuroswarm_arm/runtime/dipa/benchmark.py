"""Cascade acceptance benchmark harness for DIPA / ASCR."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.kernel import DIPARuntime

_DEFAULT_PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "type": "factual",
        "prompt": "What is the capital of France?",
        "agent_role": "classification",
        "max_tokens": 32,
    },
    {
        "type": "tool_call",
        "prompt": 'Call weather API for London and return JSON: {"city":"","temp_c":0}',
        "agent_role": "tool_call",
        "max_tokens": 64,
    },
    {
        "type": "code",
        "prompt": "Write a Python function that returns the nth Fibonacci number.",
        "agent_role": "code",
        "max_tokens": 128,
    },
    {
        "type": "summarization",
        "prompt": "Summarize speculative decoding benefits for CPU inference in two sentences.",
        "agent_role": "classification",
        "max_tokens": 64,
    },
)


@dataclass(slots=True)
class BenchmarkRequestRecord:
    prompt_type: str
    prompt: str
    tokens_proposed: int
    tokens_accepted: int
    tier_used: int
    latency_ms: float
    speedup_vs_baseline: float = 1.0


@dataclass(slots=True)
class BenchmarkResult:
    iterations: int
    avg_latency_ms: float
    overall_acceptance_rate: float
    avg_speedup_vs_baseline: float
    sample_size: int
    per_prompt_type: dict[str, dict[str, float | int]]
    per_request: list[BenchmarkRequestRecord] = field(default_factory=list)


class BenchmarkRunner:
    """Run cascade acceptance benchmarks against a wired DIPARuntime."""

    def __init__(self, runtime: DIPARuntime) -> None:
        self.runtime = runtime

    def run(
        self,
        *,
        iterations: int | None = None,
        prompts: Sequence[str | Mapping[str, Any]] | None = None,
        max_tokens: int = 64,
        agent_role: str = "tool_call",
        latency_sla_ms: float = 5000.0,
    ) -> BenchmarkResult:
        cases = _normalize_prompts(
            prompts,
            iterations=iterations,
            max_tokens=max_tokens,
            agent_role=agent_role,
        )
        records: list[BenchmarkRequestRecord] = []
        latencies: list[float] = []

        for case in cases:
            req = InferenceRequest(
                messages=[{"role": "user", "content": case["prompt"]}],
                agent_role=str(case.get("agent_role") or agent_role),
                max_tokens=int(case.get("max_tokens") or max_tokens),
                latency_sla_ms=float(case.get("latency_sla_ms") or latency_sla_ms),
            )
            out = self.runtime.infer(req)
            metrics = dict(out.metrics or {})
            proposed = _metric_int(
                metrics,
                "ascr_draft_tokens",
                "tokens_proposed",
                default=max(1, int(metrics.get("completion_tokens", 0) or 0)),
            )
            accepted = _metric_int(
                metrics,
                "ascr_accepted_tokens",
                "tokens_accepted",
                default=max(1, int(metrics.get("completion_tokens", 0) or 0)),
            )
            latency = float(metrics.get("cascade_latency_ms") or metrics.get("latency_ms") or 0.0)
            speedup = _speedup_vs_baseline(proposed, accepted, metrics)
            records.append(
                BenchmarkRequestRecord(
                    prompt_type=str(case.get("type") or "unknown"),
                    prompt=str(case["prompt"]),
                    tokens_proposed=proposed,
                    tokens_accepted=accepted,
                    tier_used=int(out.tier_used or metrics.get("tier_used", 1) or 1),
                    latency_ms=latency,
                    speedup_vs_baseline=speedup,
                )
            )
            latencies.append(latency)

        total_proposed = sum(r.tokens_proposed for r in records)
        total_accepted = sum(r.tokens_accepted for r in records)
        overall = total_accepted / max(1, total_proposed)
        avg_latency = sum(latencies) / max(1, len(latencies))
        avg_speedup = sum(r.speedup_vs_baseline for r in records) / max(1, len(records))
        per_type = _aggregate_by_type(records)

        return BenchmarkResult(
            iterations=len(records),
            avg_latency_ms=avg_latency,
            overall_acceptance_rate=overall,
            avg_speedup_vs_baseline=avg_speedup,
            sample_size=len(records),
            per_prompt_type=per_type,
            per_request=records,
        )


def _normalize_prompts(
    prompts: Sequence[str | Mapping[str, Any]] | None,
    *,
    iterations: int | None,
    max_tokens: int,
    agent_role: str,
) -> list[dict[str, Any]]:
    if prompts:
        out: list[dict[str, Any]] = []
        for item in prompts:
            if isinstance(item, str):
                out.append(
                    {
                        "type": "unknown",
                        "prompt": item,
                        "agent_role": agent_role,
                        "max_tokens": max_tokens,
                    }
                )
            else:
                out.append(
                    {
                        "type": item.get("type", "unknown"),
                        "prompt": item.get("prompt") or item.get("content") or "",
                        "agent_role": item.get("agent_role", agent_role),
                        "max_tokens": item.get("max_tokens", max_tokens),
                        "latency_sla_ms": item.get("latency_sla_ms"),
                    }
                )
        return out

    count = max(1, int(iterations or 1))
    pool = list(_DEFAULT_PROMPTS)
    return [dict(pool[i % len(pool)]) for i in range(count)]


def _metric_int(metrics: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        value = metrics.get(key)
        if value is None:
            continue
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            continue
    return default


def _speedup_vs_baseline(
    proposed: int,
    accepted: int,
    metrics: Mapping[str, Any],
) -> float:
    gain = float(metrics.get("ascr_speculation_gain", 0.0) or 0.0)
    if gain > 0:
        return max(1.0, 1.0 + gain)
    if accepted > 0 and proposed > 0:
        return max(1.0, float(proposed) / float(accepted))
    return 1.0


def _aggregate_by_type(
    records: Sequence[BenchmarkRequestRecord],
) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, list[BenchmarkRequestRecord]] = defaultdict(list)
    for record in records:
        buckets[record.prompt_type].append(record)

    out: dict[str, dict[str, float | int]] = {}
    for prompt_type, items in sorted(buckets.items()):
        proposed = sum(r.tokens_proposed for r in items)
        accepted = sum(r.tokens_accepted for r in items)
        out[prompt_type] = {
            "acceptance_rate": accepted / max(1, proposed),
            "sample_size": len(items),
            "avg_latency_ms": sum(r.latency_ms for r in items) / max(1, len(items)),
            "avg_speedup_vs_baseline": sum(r.speedup_vs_baseline for r in items)
            / max(1, len(items)),
            "avg_tier_used": sum(r.tier_used for r in items) / max(1, len(items)),
        }
    return out
