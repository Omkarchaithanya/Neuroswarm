"""NUMA / ARM adapter tests (best-effort, skip-safe)."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.arm.adapters import ArmRuntimeAdapter


def test_arm_single_numa_fallback() -> None:
    arm = ArmRuntimeAdapter({"arm": {"numa_aware": True, "report_unavailable": True}})
    placement = arm.detect(hardware=type("H", (), {"numa_nodes": 1, "features": {}, "cores": list(range(8))})())
    assert placement.draft_numa_node == 0
    assert placement.verify_numa_node == 0
    assert placement.numa_available is False
    assert placement.locality_mode == "cache_aware"
    assert placement.draft_cores == [0, 1]
    assert "UMA" in placement.message or "cache" in placement.message.lower() or "affinity" in placement.message.lower()


def test_arm_multi_numa_placement() -> None:
    arm = ArmRuntimeAdapter({"arm": {"numa_aware": True}})
    placement = arm.detect(
        hardware=type("H", (), {"numa_nodes": 2, "features": {"kleidiai": True}, "cores": list(range(16))})()
    )
    assert placement.numa_available is True
    assert placement.verify_numa_node == 1
    assert placement.kleidiai is True
    assert placement.locality_mode == "numa_aware"


def test_pin_thread_best_effort() -> None:
    arm = ArmRuntimeAdapter({"arm": {"pin_draft_pool": True}})
    arm.detect(hardware=type("H", (), {"numa_nodes": 1, "features": {}, "cores": list(range(8))})())
    # Must not raise; may return False on Windows.
    result = arm.pin_current_thread("draft")
    assert result in {True, False}
