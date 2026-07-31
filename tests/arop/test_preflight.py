"""Tests for AROP Axion preflight honesty gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neuroswarm_arm.arop.preflight import MIN_TOTAL_SAMPLES, run_preflight

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_preflight_pass_real_apx(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NSA_PERFORMIX_ALLOW_DEMO", "0")
    result = run_preflight(FIXTURES / "code_hotspots_apx.json")
    assert result.ok is True
    assert any("source=" in c for c in result.checks)
    assert any("not contaminated" in c for c in result.checks)
    assert result.errors == []


def test_preflight_fail_demo_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NSA_PERFORMIX_ALLOW_DEMO", "1")
    result = run_preflight(FIXTURES / "code_hotspots_apx.json")
    assert result.ok is False
    assert any("NSA_PERFORMIX_ALLOW_DEMO" in e for e in result.errors)


def test_preflight_fail_contaminated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NSA_PERFORMIX_ALLOW_DEMO", "0")
    result = run_preflight(FIXTURES / "code_hotspots_contaminated.json")
    assert result.ok is False
    assert any("contaminated" in e for e in result.errors)


def test_preflight_fail_low_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("NSA_PERFORMIX_ALLOW_DEMO", "0")
    payload = {
        "source": "apx",
        "hotspots": [
            {"function": "<Unknown code in libggml-cpu.so>", "pct": 80.0, "samples": 8.0},
            {"function": "__sched_yield", "pct": 20.0, "samples": 4.0},
        ],
    }
    path = tmp_path / "low_sample.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = run_preflight(path)
    assert result.ok is False
    assert any("low-sample" in e for e in result.errors)
    assert MIN_TOTAL_SAMPLES == 100


def test_preflight_fail_demo_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("NSA_PERFORMIX_ALLOW_DEMO", "0")
    path = tmp_path / "demo.json"
    path.write_text(
        json.dumps(
            {
                "source": "demo",
                "hotspots": [{"function": "x", "pct": 50.0, "samples": 500}],
            }
        ),
        encoding="utf-8",
    )
    result = run_preflight(path)
    assert result.ok is False
