"""Failure recovery + stress smoke for DIPA control plane."""

from __future__ import annotations

import time

from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.backends.sglang import SGLangBackend
from neuroswarm_arm.runtime.dipa.backends.rtp_llm import RtpLlmBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import HealthState


def test_hal_stubs_register_unavailable() -> None:
    rt = build_dipa(use_mock=True, start=False)
    rt.backends.register(SGLangBackend())
    rt.backends.register(RtpLlmBackend())
    rt.start()
    try:
        import asyncio

        statuses = asyncio.run(rt.backends.health_all())
        assert statuses["sglang"].state == HealthState.UNHEALTHY
        assert statuses["rtp_llm"].state == HealthState.UNHEALTHY
        assert "UNAVAILABLE" in statuses["sglang"].details.get("feature", "")
    finally:
        rt.shutdown()


def test_benchmark_runner_smoke() -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:
        result = rt.benchmark_runner.run(
            "mock-generate",
            lambda: rt.engine.generate([{"role": "user", "content": "bench"}], max_tokens=4),
            iterations=3,
        )
        assert result["iterations"] == 3
        assert result["latency_ms_avg"] >= 0.0
    finally:
        rt.shutdown()


def test_stress_burst_mock(iterations: int = 32) -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:
        t0 = time.perf_counter()
        for i in range(iterations):
            out = rt.engine.generate(
                [{"role": "user", "content": f"burst {i}"}],
                max_tokens=8,
                session_id=f"s{i}",
            )
            assert "text" in out
        elapsed = time.perf_counter() - t0
        assert elapsed < 60.0
        assert rt.metrics_collector.snapshot()["counters"].get("dipa.infer", 0) >= iterations
    finally:
        rt.shutdown()
