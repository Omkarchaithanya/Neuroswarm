"""Collector tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from neuroswarm_arm.metrics.collectors import PerformixCollector, PsutilCollector
from neuroswarm_arm.metrics.domains import register_all_domains
from neuroswarm_arm.metrics.registry import MetricRegistry

_WORK = Path(__file__).resolve().parents[2] / "work" / "rmf-pytest"


def _fresh_dir() -> Path:
    path = _WORK / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_psutil_collector_collect() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    col = PsutilCollector(reg, interval_s=60.0)
    col.collect()
    names = {s.name for s in reg.snapshot().series}
    # psutil may be missing in some envs; if present RSS should appear
    if col._psutil is not None:
        assert "nexus_memory_rss_bytes" in names


def test_performix_unavailable_zeros() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    base = _fresh_dir()
    col = PerformixCollector(reg, path=base / "missing.json", enabled=True)
    col.collect()
    avail = [s for s in reg.snapshot().series if s.name == "nexus_performix_available"]
    assert avail and avail[0].value == 0.0


def test_performix_snapshot() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    base = _fresh_dir()
    path = base / "perf.json"
    path.write_text(
        json.dumps(
            {
                "source": "apx",
                "available": 1,
                "cycles": 1000,
                "instructions": 2000,
                "ipc": 2.0,
                "cache_misses": 3,
            }
        ),
        encoding="utf-8",
    )
    col = PerformixCollector(reg, path=path, enabled=True)
    col.collect()
    by_name = {s.name: s.value for s in reg.snapshot().series}
    assert by_name["nexus_performix_available"] == 1.0
    assert by_name["nexus_performix_cycles"] == 1000.0
    assert by_name["nexus_performix_ipc"] == 2.0
    assert by_name["nexus_performix_snapshot_age_seconds"] >= 0.0
    assert by_name["nexus_performix_snapshot_age_seconds"] < 60.0


def _by_name(reg: MetricRegistry) -> dict[str, float]:
    return {s.name: s.value for s in reg.snapshot().series}


def test_performix_demo_source_zeros() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    path = _fresh_dir() / "demo.json"
    path.write_text(
        json.dumps(
            {
                "source": "demo",
                "available": 1,
                "cycles": 9_999_999,
                "instructions": 9_999_999,
                "ipc": 9.9,
                "cache_misses": 1200,
                "hotspots": [{"function": "fake", "pct": 99.0}],
            }
        ),
        encoding="utf-8",
    )
    PerformixCollector(reg, path=path, enabled=True).collect()
    by = _by_name(reg)
    assert by["nexus_performix_available"] == 0.0
    assert by["nexus_performix_ipc"] == 0.0
    assert by["nexus_performix_cycles"] == 0.0
    assert by["nexus_performix_hotspot_count"] == 0.0
    assert by["nexus_performix_snapshot_age_seconds"] >= 0.0


def test_performix_synthetic_source_zeros() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    path = _fresh_dir() / "syn.json"
    path.write_text(
        json.dumps({"source": "synthetic", "available": 1, "ipc": 3.0, "cycles": 100}),
        encoding="utf-8",
    )
    PerformixCollector(reg, path=path, enabled=True).collect()
    by = _by_name(reg)
    assert by["nexus_performix_available"] == 0.0
    assert by["nexus_performix_ipc"] == 0.0


def test_performix_unavailable_source_zeros() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    path = _fresh_dir() / "unavail.json"
    path.write_text(
        json.dumps(
            {
                "source": "unavailable",
                "available": 0,
                "error": "apx_missing",
                "ipc": 0.0,
                "cycles": 0.0,
            }
        ),
        encoding="utf-8",
    )
    PerformixCollector(reg, path=path, enabled=True).collect()
    by = _by_name(reg)
    assert by["nexus_performix_available"] == 0.0
    assert by["nexus_performix_ipc"] == 0.0
    assert by["nexus_performix_snapshot_age_seconds"] >= 0.0


def test_performix_available_flag_false_zeros() -> None:
    """Even with source=apx, available=0 must not look live."""
    reg = MetricRegistry()
    register_all_domains(reg)
    path = _fresh_dir() / "flag.json"
    path.write_text(
        json.dumps(
            {
                "source": "apx",
                "available": 0,
                "cycles": 5000,
                "instructions": 10000,
                "ipc": 2.0,
            }
        ),
        encoding="utf-8",
    )
    PerformixCollector(reg, path=path, enabled=True).collect()
    by = _by_name(reg)
    assert by["nexus_performix_available"] == 0.0
    assert by["nexus_performix_ipc"] == 0.0
    assert by["nexus_performix_cycles"] == 0.0


def test_performix_does_not_invent_ipc_from_zeros() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    path = _fresh_dir() / "zeros.json"
    path.write_text(
        json.dumps({"source": "apx", "available": 1, "cycles": 0, "instructions": 0}),
        encoding="utf-8",
    )
    PerformixCollector(reg, path=path, enabled=True).collect()
    by = _by_name(reg)
    assert by["nexus_performix_available"] == 1.0
    assert by["nexus_performix_ipc"] == 0.0
