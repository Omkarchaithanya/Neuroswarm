"""Draft vs verify CPU affinity (Axion UMA + Apple P/E)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from neuroswarm_arm.runtime.armcascade.arm.adapters import ArmRuntimeAdapter


def test_axion_single_uma_draft_verify_split() -> None:
    with patch(
        "neuroswarm_arm.runtime.haoe.topology.cpu_topology.read_online_cpus",
        return_value=[0, 1, 2, 3, 4, 5, 6, 7],
    ):
        # Clear VERIFY/DRAFT overrides so default_uma_partitions apply.
        with patch.dict(
            "os.environ",
            {
                "NSA_DRAFT_VERIFY_AFFINITY": "1",
                "NSA_DRAFT_CPUSET": "",
                "NSA_VERIFY_CPUSET": "",
                "NSA_TIER1_CPUSET": "0-1",
                "NSA_TIER2_CPUSET": "2-4",
                "NSA_TIER3_CPUSET": "5-7",
            },
            clear=False,
        ):
            arm = ArmRuntimeAdapter({"arm": {"numa_aware": True}})
            placement = arm.detect(
                hardware=type(
                    "H",
                    (),
                    {"numa_nodes": 1, "features": {}, "cores": list(range(8))},
                )()
            )
    assert placement.draft_cores == [0, 1]
    assert placement.verify_cores == [2, 3, 4, 5, 6, 7]
    assert placement.draft_affinity_tag != 0
    assert placement.verify_affinity_tag != 0


def test_apple_silicon_ecore_draft_pcore_verify() -> None:
    def _sysctl(cmd: list[str], **kwargs: object) -> str:
        key = cmd[-1] if cmd else ""
        if "perflevel0" in key:
            return "4\n"
        if "perflevel1" in key:
            return "4\n"
        raise AssertionError(key)

    with patch("platform.system", return_value="Darwin"), patch(
        "subprocess.check_output", side_effect=_sysctl
    ), patch.dict(
        "os.environ",
        {"NSA_APPLE_ECORE_FOR_DRAFT": "1", "NSA_DRAFT_VERIFY_AFFINITY": "1"},
        clear=False,
    ):
        arm = ArmRuntimeAdapter()
        placement = arm.detect()
    assert arm.pcore_count == 4
    assert arm.ecore_count == 4
    # P first 0-3, E 4-7 → draft=E, verify=P
    assert placement.draft_cores == [4, 5, 6, 7]
    assert placement.verify_cores == [0, 1, 2, 3]
    assert placement.draft_affinity_tag == 1  # E-core
    assert placement.verify_affinity_tag == 2  # P-core
    assert placement.locality_mode == "apple_perflevel"


def test_cpu_affinity_router_speculation_phases() -> None:
    from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan
    from neuroswarm_arm.runtime.dipa.routing.cpu_affinity_router import CpuAffinityRouter

    plan = ExecutionPlan(use_cascade=True, speculation=True)
    plan.metadata["speculation"] = {"enabled": True}
    router = CpuAffinityRouter(
        {
            "affinity_enabled": True,
            "core_partition": {
                "mode": "uma_fixed",
                "uma_draft": [0, 1],
                "uma_verify_mid": [2, 3, 4],
                "uma_verify_large": [5, 6, 7],
            },
        }
    )
    assert router.recommend("draft", plan) == [0, 1]
    assert router.recommend("verify", plan) == [5, 6, 7]
    assert plan.metadata["topology"]["affinity_draft"] == [0, 1]
    assert plan.metadata["topology"]["affinity_verify"] == [5, 6, 7]
