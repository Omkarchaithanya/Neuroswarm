"""Tests for Linux perf / eBPF profiler providers (honest unavailable paths)."""

from __future__ import annotations

from neuroswarm_arm.armora.profiling.providers.ebpf import EbpfProfilerProvider
from neuroswarm_arm.armora.profiling.providers.perf import PerfProfilerProvider
from neuroswarm_arm.armora.profiling.schemas import CapabilityState, ProfileSessionContext, ProfilingMode


def test_perf_capabilities_without_linux(monkeypatch) -> None:
    monkeypatch.setattr(
        "neuroswarm_arm.armora.profiling.providers.perf.is_linux",
        lambda: False,
    )
    monkeypatch.setattr(
        "neuroswarm_arm.armora.profiling.providers.perf.which_binary",
        lambda _n: None,
    )
    p = PerfProfilerProvider()
    caps = p.capabilities()
    assert caps.state == CapabilityState.UNAVAILABLE
    assert "not_linux" in caps.reasons


def test_ebpf_requires_env_flag(monkeypatch) -> None:
    monkeypatch.delenv("NSA_EBPF_PROFILE", raising=False)
    monkeypatch.delenv("NSA_PERF_PID", raising=False)
    monkeypatch.setattr(
        "neuroswarm_arm.armora.profiling.providers.ebpf.is_linux",
        lambda: True,
    )
    monkeypatch.setattr(
        "neuroswarm_arm.armora.profiling.providers.ebpf.which_binary",
        lambda n: "/usr/bin/bpftrace" if n == "bpftrace" else None,
    )
    p = EbpfProfilerProvider()
    caps = p.capabilities()
    assert caps.state == CapabilityState.UNAVAILABLE
    assert "NSA_EBPF_PROFILE_not_set" in caps.reasons
    session = ProfileSessionContext(
        session_id="s1",
        request_id="r1",
        mode=ProfilingMode.PRODUCTION,
    )
    batch = p.sample(session)
    assert batch.samples == []


def test_ebpf_available_when_enabled_with_pid(monkeypatch) -> None:
    monkeypatch.setenv("NSA_EBPF_PROFILE", "1")
    monkeypatch.setenv("NSA_PERF_PID", "12345")
    monkeypatch.setattr(
        "neuroswarm_arm.armora.profiling.providers.ebpf.is_linux",
        lambda: True,
    )
    monkeypatch.setattr(
        "neuroswarm_arm.armora.profiling.providers.ebpf.which_binary",
        lambda n: "/usr/bin/bpftrace" if n == "bpftrace" else None,
    )
    p = EbpfProfilerProvider()
    caps = p.capabilities()
    assert caps.state == CapabilityState.AVAILABLE
    assert caps.features.get("profile_enabled") is True
