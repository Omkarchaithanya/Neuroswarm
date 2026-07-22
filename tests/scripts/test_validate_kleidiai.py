"""Tests for benchmark-based KleidiAI validation script."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kleidiai_verifier import (
    CpuFeatureResult,
    KleidiaiVerifier,
    validate_kleidiai,
)

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "validate_kleidiai.py"
_spec = importlib.util.spec_from_file_location("validate_kleidiai_script", _SCRIPT)
assert _spec and _spec.loader
_vk = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _vk
_spec.loader.exec_module(_vk)

LLAMA_BASELINE = {
    "llama-3.2-3b-instruct-q4_0.gguf": {
        "no_kleidiai_tok_s": 19.81,
        "kleidiai_tok_s": 24.99,
        "measured_on": "test",
    }
}


def _report(
    samples: list[float],
    *,
    model: str = "llama-3.2-3b-instruct-q4_0.gguf",
    require: bool = False,
    baselines: dict | None = None,
) -> dict:
    def sample_fn(_url: str) -> float | None:
        if not samples:
            return None
        return samples.pop(0)

    return _vk.validate(
        "http://test",
        require=require,
        log_text="",
        baselines=baselines or LLAMA_BASELINE,
        sleep_fn=lambda _s: None,
        sample_fn=sample_fn,
    )


def test_load_baselines_skips_schema_metadata() -> None:
    table = _vk.load_baselines(_vk.BASELINES_PATH)
    assert "_schema" not in table
    assert "qwen2.5-0.5b-instruct-q4_0.gguf" in table
    assert table["qwen2.5-0.5b-instruct-q4_0.gguf"]["gain_pct"] == 63.77
    deepseek = table["deepseek-r1-distill-llama-8b-q8_0.gguf"]
    assert deepseek["no_kleidiai_tok_s"] == 6.78
    assert deepseek["kleidiai_tok_s"] == 9.06
    assert deepseek["gain_pct"] == 33.6


def test_baseline_reference_gain_pct_derives_when_missing() -> None:
    entry = {"no_kleidiai_tok_s": 20.0, "kleidiai_tok_s": 25.0}
    assert _vk.baseline_reference_gain_pct(entry) == 25.0


def test_benchmark_pass_median_and_gain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_vk, "resolve_model", lambda _url: "llama-3.2-3b-instruct-q4_0.gguf")
    monkeypatch.setattr(_vk, "build_log_scrape_info", lambda *_a, **_k: {"warning_lines": []})
    report = _report([24.5, 25.3, 25.1])
    assert report["ok"] is True
    assert report["benchmark"]["median_tok_s"] == 25.1
    assert report["benchmark"]["baseline_tok_s"] == 19.81
    assert report["benchmark"]["gain_pct"] == pytest.approx(((25.1 - 19.81) / 19.81) * 100, rel=1e-3)


def test_benchmark_regression_fail_with_require(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_vk, "resolve_model", lambda _url: "llama-3.2-3b-instruct-q4_0.gguf")
    monkeypatch.setattr(_vk, "build_log_scrape_info", lambda *_a, **_k: {"warning_lines": []})
    report = _report([15.0, 16.0, 15.5], require=True)
    assert report["ok"] is False
    assert report["benchmark"]["median_tok_s"] == 15.5
    assert _vk.should_exit_nonzero(report, require=True) is True


def test_benchmark_regression_warn_only_without_require(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_vk, "resolve_model", lambda _url: "llama-3.2-3b-instruct-q4_0.gguf")
    monkeypatch.setattr(_vk, "build_log_scrape_info", lambda *_a, **_k: {"warning_lines": []})
    report = _report([15.0, 16.0, 15.5], require=False)
    assert report["ok"] is False
    assert report.get("warn_only") is True
    assert _vk.should_exit_nonzero(report, require=False) is False


def test_unknown_model_exits_ok_even_with_require(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_vk, "resolve_model", lambda _url: "unknown-model.gguf")
    monkeypatch.setattr(_vk, "build_log_scrape_info", lambda *_a, **_k: {"warning_lines": []})
    report = _report([10.0, 11.0, 12.0], require=True, baselines=LLAMA_BASELINE)
    assert report["ok"] is True
    assert "no baseline" in report["message"]
    assert _vk.should_exit_nonzero(report, require=True) is False


def test_insufficient_samples_hard_fail() -> None:
    report = {
        "ok": False,
        "hard_fail": True,
        "benchmark": {"samples_tok_s": [20.0], "median_tok_s": 20.0},
        "message": "insufficient benchmark samples (1/3 succeeded)",
    }
    assert _vk.should_exit_nonzero(report, require=False) is True
    assert _vk.should_exit_nonzero(report, require=True) is True


def test_insufficient_samples_from_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_vk, "resolve_model", lambda _url: "llama-3.2-3b-instruct-q4_0.gguf")
    monkeypatch.setattr(_vk, "build_log_scrape_info", lambda *_a, **_k: {"warning_lines": []})

    calls = {"n": 0}

    def one_ok(_url: str) -> float | None:
        calls["n"] += 1
        return 21.0 if calls["n"] == 1 else None

    report = _vk.validate(
        "http://test",
        baselines=LLAMA_BASELINE,
        sleep_fn=lambda _s: None,
        sample_fn=one_ok,
    )
    assert report["hard_fail"] is True
    assert len(report["benchmark"]["samples_tok_s"]) == 1


@dataclass(slots=True)
class _SlotsProbe:
    value: int = 1


def test_serialize_verify_result_uses_asdict_not_dict() -> None:
    result = KleidiaiVerifier(require=False).result()
    payload = _vk.serialize_verify_result(result)
    assert "cpu_features" in payload
    assert isinstance(payload["cpu_features"], dict)
    assert payload["cpu_features"]["source"] == result.cpu_features.source
    # slots dataclass must not explode when serialized
    probe = _SlotsProbe()
    assert asdict(probe) == {"value": 1}


# --- kleidiai_verifier unit tests (unchanged verifier behavior) ---


def test_validate_kleidiai_raises_without_kernel_names() -> None:
    log = "load_tensors: CPU model buffer size = 1 MiB\ninfo: generic ggml init"
    with pytest.raises(RuntimeError, match="kernel names absent"):
        validate_kleidiai(log, require=True)


def test_validate_kleidiai_accepts_kai_matmul() -> None:
    log = "using kernel kai_matmul for q8_0 block"
    result = validate_kleidiai(log, require=True)
    assert result.kernel_ok is True


def test_validate_kleidiai_cpu_gate_when_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    from neuroswarm_arm.runtime.dipa.backends.llama_cpp import kleidiai_verifier

    monkeypatch.setattr(kleidiai_verifier, "_cpu_gate_enforced", lambda: True)
    cpu = CpuFeatureResult(sve2=False, i8mm=True, asimddp=True, source="test")
    log = "ggml-cpu-aarch64 backend active"
    with pytest.raises(RuntimeError, match="CPU features missing"):
        validate_kleidiai(log, require=True, cpu_features=cpu)


def test_scrape_log_info_collects_kleidiai_warnings() -> None:
    log = "kleidiai: no kernel for tensor type q4_1, not accelerated by KleidiAI"
    info = _vk.scrape_log_info(log)
    assert info["kleidiai_warnings_present"] is True
    assert info["warning_lines"]
