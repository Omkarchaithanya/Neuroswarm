"""Dual-mode locality scheduler + NUMA status tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.arm.adapters import ArmRuntimeAdapter
from neuroswarm_arm.runtime.haoe.topology.locality_scheduler import (
    build_affinity_prefix,
    default_uma_partitions,
    resolve_locality_plan,
    taskset_argv,
)
from neuroswarm_arm.runtime.haoe.topology.numa_status import (
    build_numa_bind_argv,
    collect_numa_status,
)


def test_axion_single_uma_cache_aware_partitions(monkeypatch) -> None:
    monkeypatch.setenv("NSA_LOCALITY_MODE", "auto")
    monkeypatch.delenv("NSA_TIER1_CPUSET", raising=False)
    monkeypatch.delenv("NSA_TIER2_CPUSET", raising=False)
    monkeypatch.delenv("NSA_TIER3_CPUSET", raising=False)
    topo = {0: list(range(8))}
    st = collect_numa_status(topology=topo, machine_type="c4a-standard-8", memory_bind_active=False)
    assert st.numa_nodes == 1
    assert st.cross_numa_penalty_applicable is False
    assert st.locality_mode == "cache_aware"
    assert st.core_partitions["tier1"] == [0, 1]
    assert st.core_partitions["tier2"] == [2, 3, 4]
    assert st.core_partitions["tier3"] == [5, 6, 7]
    assert all(v is None for v in st.bind_planned.values())
    assert st.omp.get("OMP_PROC_BIND") == "close"


def test_multi_numa_mode_plans_numactl(monkeypatch) -> None:
    monkeypatch.setenv("NSA_LOCALITY_MODE", "auto")
    monkeypatch.setenv("NSA_NUMA_POLICY", "auto")
    monkeypatch.setenv("NSA_NUMA_BIND", "1")
    plan = resolve_locality_plan(numa_nodes=2, online_cores=list(range(16)), multi_node=True)
    assert plan.mode == "numa_aware"
    assert build_numa_bind_argv(tier=1, nodes=[0, 1]) == [
        "numactl",
        "--cpunodebind=0",
        "--membind=0",
    ]


def test_taskset_prefix_for_cache_aware() -> None:
    plan = resolve_locality_plan(numa_nodes=1, online_cores=list(range(8)), multi_node=False)
    prefix = build_affinity_prefix(tier="tier1", plan=plan, numa_bind=None)
    assert prefix == ["taskset", "-c", "0-1"]
    assert taskset_argv([2, 3, 4]) == ["taskset", "-c", "2-4"]


def test_default_uma_partitions_8() -> None:
    p = default_uma_partitions(8)
    assert p["tier1"] == [0, 1]
    assert len(p["tier2"]) + len(p["tier3"]) == 6


def test_arm_adapter_single_uma_exposes_cores() -> None:
    arm = ArmRuntimeAdapter({"arm": {"numa_aware": True, "report_unavailable": True}})
    placement = arm.detect(hardware=type("H", (), {"numa_nodes": 1, "features": {}, "cores": list(range(8))})())
    assert placement.numa_available is False
    assert placement.locality_mode == "cache_aware"
    assert placement.draft_cores == [0, 1]
    assert 2 in placement.verify_cores


def test_arm_adapter_multi_numa() -> None:
    arm = ArmRuntimeAdapter({"arm": {"numa_aware": True}})
    placement = arm.detect(
        hardware=type("H", (), {"numa_nodes": 2, "features": {"kleidiai": True}, "cores": list(range(16))})()
    )
    assert placement.numa_available is True
    assert placement.verify_numa_node == 1
    assert placement.locality_mode == "numa_aware"
