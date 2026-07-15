"""Benchmark hooks for DIPA."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..interfaces.types import InferenceRequest
from ..router.request_router import RequestRouter

if TYPE_CHECKING:
    from ..kernel import DIPARuntime


@dataclass
class BenchmarkResult:
    iterations: int
    total_ms: float
    avg_latency_ms: float
    samples: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BenchmarkRunner:
    def __init__(self, runtime: DIPARuntime) -> None:
        self.runtime = runtime
        self.router = RequestRouter()

    def run(
        self,
        prompt: str = "benchmark",
        *,
        iterations: int = 5,
        agent_role: str = "classification",
    ) -> BenchmarkResult:
        samples: list[float] = []
        t0 = time.monotonic()
        for _ in range(iterations):
            req = self.router.normalize(
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "agent_role": agent_role,
                    "max_tokens": 64,
                }
            )
            s = time.monotonic()
            self.runtime.infer(req)
            samples.append((time.monotonic() - s) * 1000.0)
        total = (time.monotonic() - t0) * 1000.0
        return BenchmarkResult(
            iterations=iterations,
            total_ms=total,
            avg_latency_ms=sum(samples) / max(len(samples), 1),
            samples=samples,
            metadata={"agent_role": agent_role},
        )
