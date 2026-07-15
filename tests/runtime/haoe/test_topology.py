"""Topology / affinity / feature detection tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.haoe.interfaces.types import FeatureStatus
from neuroswarm_arm.runtime.haoe.providers import NoOpAffinityProvider, build_affinity_provider
from neuroswarm_arm.runtime.haoe.topology.cpu_topology import parse_cpu_list
from neuroswarm_arm.runtime.haoe.topology.feature_detector import (
    FeatureDetector,
    parse_cpuinfo_features,
)
from neuroswarm_arm.runtime.haoe.topology.hardware_detector import HardwareDetector
from neuroswarm_arm.runtime.haoe.topology.topology_service import TopologyService


def test_parse_cpu_list() -> None:
    assert parse_cpu_list("0-3,8,10-11") == [0, 1, 2, 3, 8, 10, 11]


def test_parse_cpuinfo_features() -> None:
    text = "Features\t: fp asimd evtstrm aes pmull sha1 sve sve2 i8mm dotprod\n"
    flags = parse_cpuinfo_features(text)
    assert "sve2" in flags
    assert "i8mm" in flags


def test_hardware_detector_override_cores() -> None:
    snap = HardwareDetector(override_cores=[0, 1, 2, 3], fast_core_fraction=0.5).detect()
    assert snap.topology.logical_cpus == [0, 1, 2, 3]
    assert len(snap.topology.fast_cores) == 2
    svc = TopologyService(snap)
    assert svc.cpu_count() == 4
    # On Windows / Axion-like envs, NUMA/MTE typically unavailable — never raises
    assert svc.feature("mte") in {
        FeatureStatus.UNAVAILABLE,
        FeatureStatus.UNKNOWN,
        FeatureStatus.AVAILABLE,
    }


def test_noop_affinity_on_unsupported() -> None:
    provider = NoOpAffinityProvider()
    assert provider.bind([0]) is False
    # build_affinity_provider should not raise
    p = build_affinity_provider(enabled=True)
    assert p.current()  # at least one logical cpu reported
