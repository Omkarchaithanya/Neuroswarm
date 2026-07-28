"""Import smoke for benchmarks/governor_live.py (no live HTTP)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "benchmarks" / "governor_live.py"


def _load_governor_live():
    spec = importlib.util.spec_from_file_location("governor_live_bench", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_governor_live_module_imports() -> None:
    mod = _load_governor_live()
    assert hasattr(mod, "run_live_governor")
    assert hasattr(mod, "PLAN_LOOSE")
    assert hasattr(mod, "PLAN_TIGHT")


def test_governor_live_http_mocked() -> None:
    mod = _load_governor_live()
    fake = {
        "status": "ok",
        "sample_size": 2,
        "pct_reduction": 55.0,
        "mean_cap_loose": 4096,
        "mean_cap_tight": 256,
    }
    with patch.object(mod, "run_live_governor", return_value=fake):
        result = mod.run_live_governor()
    assert result["status"] == "ok"
    assert result["sample_size"] > 0


@pytest.mark.live
@pytest.mark.skip(reason="requires live tier3 server")
def test_governor_live_http() -> None:
    mod = _load_governor_live()
    result = mod.run_live_governor()
    assert result["status"] == "ok"
    assert result["sample_size"] > 0
