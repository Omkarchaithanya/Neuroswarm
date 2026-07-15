"""Unit + integration tests for ARMORA Runtime Profiling Framework."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.armora.profiling import (
    MockProfilerProvider,
    ProfilingMode,
    RuntimeProfile,
    build_rpf,
    load_rpf_config,
)
from neuroswarm_arm.armora.profiling.providers.base import BaseProfilerProvider
from neuroswarm_arm.armora.profiling.registry import FailureIsolatingProxy, ProfilerRegistry
from neuroswarm_arm.armora.profiling.schemas import (
    BackendMetrics,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)

_ROOT = Path(__file__).resolve().parents[3] / "work" / "test-rpf"


@pytest.fixture()
def work() -> Path:
    path = _ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_schemas_immutable() -> None:
    profile = RuntimeProfile(request_id="r1", profiler_used="mock")
    with pytest.raises(Exception):
        profile.request_id = "x"  # type: ignore[misc]


def test_build_rpf_mock_roundtrip(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    monkeypatch.setenv("NSA_RPF_ENABLED", "1")
    rpf = build_rpf(work_dir=work)
    ctx = rpf.open_session(request_id="req-1", agent_id="agent-a", workflow_id="chat")
    assert ctx.session_id
    rpf.record_phase(ctx.session_id, planner_ms=12.5, execution_ms=100.0, backend="llama.cpp")
    rpf.sample(ctx.session_id)
    profile = rpf.finalize_sync(ctx.session_id)
    assert isinstance(profile, RuntimeProfile)
    assert profile.profiler_used == "mock"
    assert profile.planner.planner_time_ms == 12.5
    assert profile.execution.execution_time_ms == 100.0
    assert profile.backend.backend == "llama.cpp"
    text = rpf.export_prometheus()
    assert "profile_sessions_total" in text
    assert "profile_" in text
    rpf.shutdown()


def test_disabled_mode_never_raises(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_ENABLED", "0")
    rpf = build_rpf(work_dir=work)
    assert rpf.config.mode == ProfilingMode.DISABLED
    ctx = rpf.open_session(request_id="r")
    rpf.sample(ctx.session_id)
    profile = rpf.finalize_sync(ctx.session_id)
    assert profile.mode == ProfilingMode.DISABLED or profile.profiler_used in {
        "mock",
        "none",
        "error",
    }


def test_capability_cascade_prefers_available(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "auto")
    monkeypatch.setenv("NSA_RPF_ALLOW_PERFORMIX", "0")
    cfg = load_rpf_config(work_dir=work)
    reg = ProfilerRegistry(cfg)
    caps = reg.all_capabilities()
    assert "mock" in caps
    assert caps["mock"].available is True
    proxy = reg.select()
    assert proxy.name in {"perf", "psutil", "mock"}


def test_provider_override_mock(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    cfg = load_rpf_config(work_dir=work)
    proxy = ProfilerRegistry(cfg).select()
    assert proxy.name == "mock"


def test_failure_isolating_proxy_demotes() -> None:
    class Boom(BaseProfilerProvider):
        name = "boom"

        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(name=self.name, available=True)

        def sample(self, session: ProfileSessionContext) -> MetricBatch:
            raise RuntimeError("boom")

    boom = Boom()
    mock = MockProfilerProvider()
    proxy = FailureIsolatingProxy(boom, [mock], max_failures=1)
    session = ProfileSessionContext(request_id="x")
    _ = proxy.sample(session)
    assert proxy.name == "mock"
    batch = proxy.sample(session)
    assert batch.provider == "mock"
    assert len(batch.samples) > 0


def test_feedback_ranks(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    rpf = build_rpf(work_dir=work)
    for i, backend in enumerate(["a", "b", "a"]):
        ctx = rpf.open_session(request_id=f"r{i}")
        rpf.record_phase(
            ctx.session_id,
            execution_ms=50.0 + i * 10,
            backend=backend,
        )
        rpf.sample(ctx.session_id)
        rpf.finalize_sync(ctx.session_id)
    ranks = rpf.feedback.hottest_backends_sync(limit=5)
    assert ranks.objective == "hottest_backend"
    assert len(ranks.choices) >= 1
    vec = rpf.feedback.observation_vector(
        RuntimeProfile(profiler_used="mock", backend=BackendMetrics(backend="a"))
    )
    assert "cpu_percent" in vec
    assert "ipc" in vec


def test_signal_bus_connector(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    rpf = build_rpf(work_dir=work)
    ctx = rpf.open_session(request_id="bus")
    rpf.connector.record_planner(ctx.session_id, 7.0)
    rpf.connector.record_execution(ctx.session_id, 42.0)
    profile = rpf.finalize_sync(ctx.session_id)
    assert profile.planner.planner_time_ms == 7.0
    assert profile.execution.execution_time_ms == 42.0


def test_export_json_persisted(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    monkeypatch.setenv("NSA_RPF_EXPORTER", "json")
    rpf = build_rpf(work_dir=work)
    ctx = rpf.open_session(request_id="persist")
    rpf.sample(ctx.session_id)
    profile = rpf.finalize_sync(ctx.session_id)
    path = work / f"{profile.profile_id}.json"
    assert path.exists() or (work / "profiles.jsonl").exists()


def test_benchmark_overhead_bound(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    rpf = build_rpf(work_dir=work)
    start = time.perf_counter()
    for i in range(50):
        ctx = rpf.open_session(request_id=f"b{i}")
        rpf.sample(ctx.session_id)
        rpf.finalize_sync(ctx.session_id)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0


def test_psutil_provider_if_available() -> None:
    from neuroswarm_arm.armora.profiling.providers.psutil import PsutilProfilerProvider

    p = PsutilProfilerProvider()
    caps = p.capabilities()
    if not caps.available:
        pytest.skip("psutil not available")
    session = ProfileSessionContext(request_id="ps")
    p.start(session)
    batch = p.sample(session)
    assert batch.provider == "psutil"
    names = {s.name for s in batch.samples}
    assert "cpu.usage_percent" in names or "memory.rss_bytes" in names


def test_arop_provider_health(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_RPF_PROVIDER", "mock")
    from neuroswarm_arm.armora.profiling.arop_provider import ProfilingObservationProvider
    from neuroswarm_arm.evolution.models.observation import TimeWindow

    rpf = build_rpf(work_dir=work)
    ctx = rpf.open_session(request_id="arop")
    rpf.sample(ctx.session_id)
    rpf.finalize_sync(ctx.session_id)
    provider = ProfilingObservationProvider(rpf)
    h = provider.health()
    assert h.provider == "rpf"
    snap = provider.snapshot()
    assert "rpf" in snap.providers
    obs = provider.collect(TimeWindow.last_seconds(3600))
    assert isinstance(obs, list)
