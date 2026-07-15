"""Async buffer and stress tests."""

from __future__ import annotations

import time

from neuroswarm_arm.metrics.buffer import AsyncMetricBuffer
from neuroswarm_arm.metrics.domains import register_all_domains
from neuroswarm_arm.metrics.registry import MetricRegistry
from neuroswarm_arm.metrics.schemas import MetricUpdate, MetricUpdateOp


def test_buffer_flush() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    buf = AsyncMetricBuffer(reg, max_size=1024, flush_ms=10, flush_batch=64)
    for _ in range(100):
        buf.push(
            MetricUpdate(
                name="nexus_request_total",
                op=MetricUpdateOp.INC,
                value=1.0,
                labels={"status": "ok", "request_type": "http", "streaming": "false", "reasoning": "false", "agent_type": "g"},
            )
        )
    flushed = buf.flush()
    assert flushed == 100
    series = [s for s in reg.snapshot().series if s.name == "nexus_request_total"]
    assert series and series[0].value == 100.0


def test_buffer_drop_under_pressure() -> None:
    reg = MetricRegistry()
    buf = AsyncMetricBuffer(reg, max_size=8, flush_ms=1000, flush_batch=1)
    ok = 0
    for _ in range(20):
        if buf.push(
            MetricUpdate(name="nexus_request_total", op=MetricUpdateOp.INC, value=1.0, labels={})
        ):
            ok += 1
    assert buf.drops >= 1
    assert ok == 8


def test_stress_observe_throughput() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    labels = {
        "status": "ok",
        "request_type": "http",
        "streaming": "false",
        "reasoning": "false",
        "agent_type": "stress",
    }
    n = 5000
    t0 = time.perf_counter()
    for i in range(n):
        reg.observe("nexus_request_duration_seconds", (i % 50) / 1000.0, labels=labels)
    elapsed = time.perf_counter() - t0
    rate = n / elapsed if elapsed else n
    assert rate > 1000.0  # should stay well above 1k observes/sec on CI hosts
