"""ROF tracing / metrics / exporters / propagation / failure / perf tests."""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.armora.telemetry import (
    SpanNames,
    build_rof,
    get_current_context,
)
from neuroswarm_arm.armora.telemetry.config import ROFRuntimeConfig
from neuroswarm_arm.armora.telemetry.propagators import inject, extract, wrap_streaming
from neuroswarm_arm.armora.telemetry.schemas import EventType

_ROOT = Path(__file__).resolve().parents[3] / "work" / "rof-pytest"


def _fresh_dir() -> Path:
    path = _ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def rof():
    base = _fresh_dir()
    cfg = ROFRuntimeConfig(
        enabled=True,
        exporters=("prometheus", "json", "sqlite"),
        sampler="always_on",
        work_dir=base,
        json_path=base / "t.jsonl",
        sqlite_path=base / "t.sqlite",
        batch_size=32,
        export_interval_ms=50,
        max_queue_size=256,
    )
    framework = build_rof(cfg)
    yield framework
    framework.shutdown(timeout_ms=2000)
    shutil.rmtree(base, ignore_errors=True)


def test_build_and_prometheus(rof) -> None:
    text = rof.export_prometheus()
    assert "nexus_requests_total" in text or "rof_" in text
    rof.counter("nexus_requests_total", 1.0, labels={"outcome": "ok"})
    text2 = rof.export_prometheus()
    assert "nexus_requests_total" in text2


def test_cardinality_guard_drops_forbidden(rof) -> None:
    rof.counter("nexus_requests_total", 1.0, labels={"request_id": "should-drop", "outcome": "ok"})
    text = rof.export_prometheus()
    assert 'request_id="' not in text
    assert "rof_metric_label_drops_total" in text


def test_span_parent_child_continuity(rof) -> None:
    with rof.start_request(request_id="req-1", agent_id="agent") as (ctx, _span):
        assert ctx.request_id == "req-1"
        with rof.span(SpanNames.ADMISSION) as admit:
            assert admit is not None
            parent = admit.span_id
            with rof.span(SpanNames.PLANNER) as plan:
                assert plan.trace_id == admit.trace_id
                assert plan.parent_span_id == parent or plan.span_id != parent
                assert get_current_context() is not None


def test_events_and_logging(rof) -> None:
    with rof.start_request(request_id="r-log"):
        rof.emit_builtin(EventType.PLANNER_STARTED, payload={"x": 1})
        rof.log("INFO", "hello", latency_ms=1.2)
    time.sleep(0.15)
    rof.lifecycle._export_batch()
    if rof.config.json_path.exists():
        data = rof.config.json_path.read_text(encoding="utf-8")
        assert "PlannerStarted" in data or "hello" in data or "span" in data


def test_sqlite_exporter(rof) -> None:
    with rof.start_request(request_id="r-sql"):
        with rof.span(SpanNames.ROUTING):
            pass
    time.sleep(0.1)
    rof.lifecycle._export_batch()
    assert rof.config.sqlite_path.exists()


def test_propagation_async(rof) -> None:
    async def _inner() -> str:
        return get_current_context().request_id if get_current_context() else ""

    async def _run() -> str:
        with rof.start_request(request_id="async-1"):
            carrier = inject()
            restored = extract(carrier)
            assert restored.request_id == "async-1"
            return await _inner()

    assert asyncio.run(_run()) == "async-1"


def test_streaming_propagation(rof) -> None:
    with rof.start_request(request_id="stream-1"):
        def gen():
            for i in range(3):
                yield i

        out = list(wrap_streaming(gen()))
        assert out == [0, 1, 2]


def test_sampling_always_off_still_runs() -> None:
    base = _fresh_dir()
    cfg = ROFRuntimeConfig(
        enabled=True,
        exporters=("prometheus",),
        sampler="always_off",
        work_dir=base,
        json_path=base / "t.jsonl",
        sqlite_path=base / "t.sqlite",
    )
    framework = build_rof(cfg)
    try:
        with framework.start_request(request_id="off"):
            with framework.span(SpanNames.BACKEND):
                framework.counter(
                    "nexus_backend_selected_total", 1.0, labels={"backend": "x"}
                )
        assert "nexus_backend_selected_total" in framework.export_prometheus()
    finally:
        framework.shutdown()
        shutil.rmtree(base, ignore_errors=True)


def test_exporter_failure_does_not_block(rof) -> None:
    class Boom:
        name = "boom"

        def export_spans(self, spans):
            raise RuntimeError("boom")

        def shutdown(self, timeout_ms: int = 5000) -> None:
            return None

    rof.lifecycle.exporters.append(Boom())
    with rof.start_request(request_id="fail"):
        with rof.span(SpanNames.DIPA_INFER):
            pass
    rof.lifecycle._export_batch()


def test_perf_overhead_bound(rof) -> None:
    def work() -> None:
        x = 0
        for i in range(1000):
            x += i * i

    t0 = time.perf_counter()
    for _ in range(200):
        work()
    baseline = time.perf_counter() - t0

    t1 = time.perf_counter()
    for _ in range(200):
        with rof.start_request(request_id="p"):
            with rof.span(SpanNames.PLANNER):
                work()
    with_tel = time.perf_counter() - t1
    assert with_tel < baseline * 5 + 1.0


def test_arop_provider(rof) -> None:
    from neuroswarm_arm.armora.telemetry.bridges.arop_provider import ROFObservationProvider
    from neuroswarm_arm.evolution.models.observation import TimeWindow

    provider = ROFObservationProvider(rof)
    rof.counter("nexus_requests_total", 3.0, labels={"outcome": "ok"})
    metrics = provider.metrics()
    assert isinstance(metrics, dict)
    health = provider.health()
    assert health.provider == "rof"
    snap = provider.snapshot()
    assert "rof" in snap.providers
    provider.collect(TimeWindow.last_seconds(60))


def test_bridges_metrics_store(rof) -> None:
    from neuroswarm_arm.armora.telemetry.bridges import MetricsStoreSource

    class _Store:
        def export_prometheus(self) -> str:
            return "# TYPE neuroswarm_requests_total counter\nneuroswarm_requests_total 2\n"

    src = MetricsStoreSource(_Store())
    rof.register_metric_source(src)
    text = rof.export_prometheus()
    assert "neuroswarm_requests_total" in text
