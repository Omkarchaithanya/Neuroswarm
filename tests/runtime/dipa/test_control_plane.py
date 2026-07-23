"""Unit tests — DIPA control plane + ARMORA + KleidiAI verifier."""

from __future__ import annotations

import threading
import time

import pytest

from neuroswarm_arm.armora import ArmoraClient, ArmoraBudgetPolicy, BudgetConfig, build_armora
from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kleidiai_verifier import (
    KLEIDIAI_PATTERN,
    KleidiaiVerifier,
)
from neuroswarm_arm.runtime.dipa.control.hardware_detector import ControlHardwareDetector
from neuroswarm_arm.runtime.dipa.control.lifecycle_manager import LifecycleManager
from neuroswarm_arm.runtime.dipa.control.metrics_collector import MetricsCollector
from neuroswarm_arm.runtime.dipa.control.model_manager import ModelManager
from neuroswarm_arm.runtime.dipa.control.request_queue import RequestQueue
from neuroswarm_arm.runtime.dipa.control.telemetry_exporter import TelemetryExporter
from neuroswarm_arm.runtime.dipa.interfaces.lifecycle import LifecyclePhase


def test_build_dipa_mock_control_plane() -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:
        assert rt.lifecycle_manager.phase() == LifecyclePhase.READY
        assert "tier1" in rt.backends.list()
        handle = rt.engine.load_model("mock://tier1", options={"backend": "tier1"})
        assert handle.startswith("mdl_")
        out = rt.engine.generate(
            [{"role": "user", "content": "hello nexus"}],
            model="cascade",
            max_tokens=16,
        )
        assert "text" in out
        health = rt.engine.health()
        assert "state" in health or "backends" in health
        metrics = rt.engine.metrics()
        assert "lifecycle" in metrics or "kernel" in metrics
        warm = rt.engine.warmup()
        assert "backends" in warm or warm.get("ok")
    finally:
        rt.engine.shutdown()


def test_armora_facade_api() -> None:
    rt = build_dipa(use_mock=True, start=True)
    client = build_armora(rt.engine, budget=BudgetConfig(max_cost_usd=1.0))
    try:
        assert isinstance(client, ArmoraClient)
        client.load_model("m1")
        result = client.generate([{"role": "user", "content": "hi"}])
        assert result["text"] is not None
        chunks = list(client.stream([{"role": "user", "content": "stream me"}]))
        assert chunks
        assert client.health()
        assert "budget" in client.metrics()
    finally:
        client.shutdown()


def test_kleidiai_verifier_matches_upstream_log() -> None:
    line = "load_tensors: CPU_KLEIDIAI model buffer size =  3474.00 MiB"
    assert KLEIDIAI_PATTERN.search(line)
    v = KleidiaiVerifier(require=True)
    assert v.feed(line) is True
    assert v.result().ok is True
    v2 = KleidiaiVerifier(require=True)
    v2.feed("load_tensors: CPU model buffer size = 1 MiB")
    with pytest.raises(RuntimeError):
        v2.assert_ready()


def test_kleidiai_verifier_kai_matmul_kernel() -> None:
    v = KleidiaiVerifier(require=True)
    assert v.feed("kai_matmul: running") is True
    assert v.result().kernel_ok is True


def test_kleidiai_verifier_ggml_cpu_aarch64() -> None:
    v = KleidiaiVerifier(require=True)
    assert v.feed("backend ggml-cpu-aarch64 selected") is True
    assert v.result().kernel_ok is True


def test_request_queue_priority_and_reject() -> None:
    q = RequestQueue(maxsize=2)
    a = q.enqueue("a", priority=0)
    b = q.enqueue("b", priority=5)
    assert b.priority > a.priority
    first = q.dequeue(timeout_s=0.5)
    assert first is not None and first.payload == "b"
    q.enqueue("c")
    with pytest.raises(RuntimeError, match="full"):
        q.enqueue("d")


def test_lifecycle_ordered_hooks() -> None:
    lm = LifecycleManager()
    seen: list[str] = []
    for phase in (
        LifecyclePhase.DETECTING,
        LifecyclePhase.AFFINITY,
        LifecyclePhase.BACKENDS,
        LifecyclePhase.MODELS,
        LifecyclePhase.WARMUP,
        LifecyclePhase.READY,
    ):
        lm.on(phase, lambda p=phase: seen.append(p.value))
    lm.start()
    assert seen == [
        "detecting",
        "affinity",
        "backends",
        "models",
        "warmup",
        "ready",
    ]
    lm.stop()
    assert lm.phase() == LifecyclePhase.STOPPED


def test_hardware_detector_smoke() -> None:
    profile = ControlHardwareDetector().detect()
    assert profile.cpu_count >= 1
    assert "arch" in profile.to_dict()


def test_telemetry_exporter_records_without_otel() -> None:
    m = MetricsCollector()
    t = TelemetryExporter(enabled=False, endpoint="", metrics=m)
    with t.span("inference.request", backend="mock"):
        t.record_token(3, backend="mock")
        t.record_retry()
        t.record_timeout()
        t.record_cancel()
        t.record_kv_alloc(hit=True)
    snap = t.snapshot()
    assert snap["enabled"] is False
    assert "counters" in snap["metrics"]


def test_model_manager_idempotent_load() -> None:
    mm = ModelManager()
    h1 = mm.load("ref-a", backend="tier1")
    h2 = mm.load("ref-a", backend="tier1")
    assert h1 == h2
    assert mm.unload(h1) is True


def test_concurrency_infer_mock() -> None:
    rt = build_dipa(use_mock=True, start=True)
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            rt.engine.generate([{"role": "user", "content": "c"}], max_tokens=8)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    rt.shutdown()
    assert not errors


def test_armora_budget_reject() -> None:
    policy = ArmoraBudgetPolicy(BudgetConfig(max_cost_usd=0.01))
    assert policy.charge(0.005) is True
    assert policy.charge(0.01) is False
