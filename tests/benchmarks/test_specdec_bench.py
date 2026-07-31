"""SpecDec benchmark smoke tests (mock mode)."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / "benchmarks"
if str(BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REQUIRED_KEYS = (
    "tokens_per_sec",
    "acceptance_rate",
    "mean_accepted_prefix_len",
    "p50_ttft_ms",
    "p95_ttft_ms",
    "mean_draft_ms",
    "mean_verify_ms",
    "ascr_speculation_gain",
)


def _finite_walk(obj: object, path: str = "root") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _finite_walk(v, f"{path}.{k}")
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            _finite_walk(v, f"{path}[{i}]")
        return
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        assert math.isfinite(float(obj)), f"non-finite at {path}: {obj}"


@pytest.fixture(scope="module")
def bench_payload() -> dict:
    os.environ["NSA_SPECDEC_BENCH"] = "1"
    out_dir = REPO_ROOT / "work" / "benchmarks" / "test-specdec"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "specdec_bench.json"
    from specdec_bench import run_specdec_bench, write_json

    payload = run_specdec_bench(live=False)
    write_json(out, payload)
    assert out.is_file()
    return json.loads(out.read_text(encoding="utf-8"))


def test_specdec_bench_has_expected_keys(bench_payload: dict) -> None:
    assert bench_payload.get("status") in {"ok", "skipped"}
    for key in REQUIRED_KEYS:
        assert key in bench_payload, f"missing top-level key {key}"
        assert key in (bench_payload.get("overall") or {}), f"missing overall.{key}"


def test_specdec_speculation_gain_positive(bench_payload: dict) -> None:
    if bench_payload.get("status") == "skipped":
        pytest.skip("specdec_bench disabled")
    gain = float(bench_payload["ascr_speculation_gain"])
    assert gain > 0.0


def test_specdec_metrics_finite(bench_payload: dict) -> None:
    # Drop bulky rows for walk speed but still check overall aggregates.
    slim = {k: v for k, v in bench_payload.items() if k != "rows"}
    _finite_walk(slim)
    for row in (bench_payload.get("rows") or [])[:5]:
        _finite_walk(row, "row")
