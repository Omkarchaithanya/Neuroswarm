"""NUMA status + topology-gated bind tests."""

from __future__ import annotations

import os
from unittest.mock import patch

from neuroswarm_arm.runtime.dipa.topology.numa_adapter import NumaAdapter
from neuroswarm_arm.runtime.haoe.topology.numa_status import (
    build_numa_bind_argv,
    collect_numa_status,
    llama_numa_flag,
)


def test_single_node_no_cross_numa_and_no_bind(monkeypatch) -> None:
    monkeypatch.delenv("NSA_NUMA_POLICY", raising=False)
    monkeypatch.delenv("NSA_NUMA_BIND", raising=False)
    monkeypatch.setenv("NSA_LOCALITY_MODE", "auto")
    topo = {0: [0, 1, 2, 3, 4, 5, 6, 7]}
    st = collect_numa_status(topology=topo, machine_type="c4a-standard-8", memory_bind_active=False)
    assert st.numa_nodes == 1
    assert st.multi_node is False
    assert st.cross_numa_penalty_applicable is False
    assert st.policy == "single_uma"
    assert st.locality_mode == "cache_aware"
    assert all(v is None for v in st.bind_planned.values())
    assert st.llama_numa is None
    assert build_numa_bind_argv(tier=1, nodes=[0]) is None
    assert build_numa_bind_argv(tier=2, nodes=[0], policy="force") is None
    assert llama_numa_flag([0]) is None


def test_multi_node_auto_plans_bind(monkeypatch) -> None:
    monkeypatch.setenv("NSA_NUMA_POLICY", "auto")
    monkeypatch.setenv("NSA_NUMA_BIND", "1")
    topo = {0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}
    st = collect_numa_status(topology=topo, machine_type=None, memory_bind_active=False)
    assert st.numa_nodes == 2
    assert st.cross_numa_penalty_applicable is True
    assert st.bind_planned["tier1"] == ["numactl", "--cpunodebind=0", "--membind=0"]
    assert st.bind_planned["tier2"] == ["numactl", "--cpunodebind=1", "--membind=1"]
    assert st.llama_numa == "isolate"
    assert st.policy in {"numa_split_ready", "numa_bind_active"}


def test_multi_node_policy_off_no_bind(monkeypatch) -> None:
    monkeypatch.setenv("NSA_NUMA_POLICY", "off")
    argv = build_numa_bind_argv(tier=1, nodes=[0, 1], policy="off")
    assert argv is None
    st = collect_numa_status(
        topology={0: [0], 1: [1]},
        memory_bind_active=False,
    )
    assert st.cross_numa_penalty_applicable is True
    assert all(v is None for v in st.bind_planned.values())
    assert st.policy == "numa_split_ready"


def test_dipa_numa_adapter_uses_topology_service() -> None:
    class FakeTopo:
        def numa_nodes(self):
            return [0, 1]

        def cores_for_node(self, node: int):
            return [0, 1] if node == 0 else [2, 3]

    adapter = NumaAdapter(topology=FakeTopo())
    assert adapter.nodes() == [0, 1]
    assert adapter.preferred() == 0
    assert adapter.cores_for_node(1) == [2, 3]


def test_force_on_single_node_still_no_bind(monkeypatch) -> None:
    monkeypatch.setenv("NSA_NUMA_POLICY", "force")
    st = collect_numa_status(topology={0: list(range(8))}, memory_bind_active=False)
    assert st.policy == "single_uma"
    assert "force" in st.reason.lower() or "nodes==1" in st.reason
    assert all(v is None for v in st.bind_planned.values())


def test_process_supervisor_appends_numa_isolate(tmp_path) -> None:
    from neuroswarm_arm.runtime.dipa.backends.llama_cpp.process_supervisor import ProcessSupervisor

    captured: dict = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = list(cmd)
            self.pid = 4242
            self.stdout = iter(())

        def poll(self):
            return None

    with patch(
        "neuroswarm_arm.runtime.dipa.backends.llama_cpp.process_supervisor.subprocess.Popen",
        FakePopen,
    ):
        sup = ProcessSupervisor(log_dir=tmp_path)
        sup.start(
            "tier1",
            ["llama-server", "-m", "x.gguf"],
            base_url="http://127.0.0.1:8080",
            numa_bind=["numactl", "--cpunodebind=0", "--membind=0"],
        )
    assert captured["cmd"][:3] == ["numactl", "--cpunodebind=0", "--membind=0"]
    assert captured["cmd"][-2:] == ["--numa", "isolate"]
