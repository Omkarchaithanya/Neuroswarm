"""Tests for Performix telemetry bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from neuroswarm_arm.telemetry.performix_bridge import PerformixBridge, get_performix_bridge


def test_sample_pmu_parses_recipe_output() -> None:
    bridge = PerformixBridge(mcp_url="")
    bridge._available = True
    bridge._client = MagicMock()
    bridge._client.recipe_run.return_value = {
        "parsed": {
            "l3_miss_rate": 0.12,
            "sve_util_pct": 45.5,
            "branch_mispredict_pct": 1.1,
        }
    }
    attrs = bridge.sample_pmu(pid=1234, duration_ms=100)
    assert attrs["gen_ai.arm.l3_miss_rate"] == 0.12
    assert attrs["gen_ai.arm.sve_util_pct"] == 45.5
    assert attrs["gen_ai.arm.branch_mispredict_pct"] == 1.1


def test_sample_pmu_fail_soft_when_unavailable() -> None:
    bridge = PerformixBridge(mcp_url="")
    bridge._available = False
    assert bridge.sample_pmu(pid=1) == {}


def test_schedule_sample_no_crash_when_mcp_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("NSA_PERFORMIX_SAMPLE", "1")
    bridge = PerformixBridge(mcp_url="")
    bridge._available = False
    with patch("neuroswarm_arm.telemetry.performix_bridge.get_performix_bridge", return_value=bridge):
        bridge.schedule_sample(op="kv_load", session_id="s1")
    # no exception


def test_list_tools_called_on_init() -> None:
    with patch("neuroswarm_arm.evolution.performix_mcp_client.PerformixMCPClient") as mock_cls:
        inst = mock_cls.return_value
        inst.list_tools.return_value = ["apx_recipe_run"]
        inst.mcp_url = "http://localhost:8090"
        bridge = PerformixBridge(mcp_url="http://localhost:8090")
        inst.list_tools.assert_called()
        assert bridge.available is True
