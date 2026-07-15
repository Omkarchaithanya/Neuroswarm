"""Topology package exports."""

from __future__ import annotations

from .affinity_manager import AffinityManager
from .cpu_topology import CPUTopology, parse_cpu_list
from .feature_detector import FeatureDetector, FeatureSet, parse_cpuinfo_features
from .hardware_detector import HardwareDetector, HardwareSnapshot
from .numa_adapter import NumaAdapter, NumaPlacement
from .thread_pinning import ThreadPinning
from .topology_service import TopologyService

__all__ = [
    "AffinityManager",
    "CPUTopology",
    "parse_cpu_list",
    "FeatureDetector",
    "FeatureSet",
    "parse_cpuinfo_features",
    "HardwareDetector",
    "HardwareSnapshot",
    "NumaAdapter",
    "NumaPlacement",
    "ThreadPinning",
    "TopologyService",
]
