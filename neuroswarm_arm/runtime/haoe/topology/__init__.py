"""Topology package exports."""

from __future__ import annotations

from .affinity_manager import AffinityManager
from .cpu_topology import CPUTopology, parse_cpu_list
from .feature_detector import FeatureDetector, FeatureSet, parse_cpuinfo_features
from .hardware_detector import HardwareDetector, HardwareSnapshot
from .numa_adapter import NumaAdapter, NumaPlacement
from .numa_status import (
    NumaStatus,
    build_numa_bind_argv,
    collect_numa_status,
    llama_numa_flag,
    publish_numa_metrics,
)
from .locality_scheduler import (
    LocalityPlan,
    build_affinity_prefix,
    resolve_locality_plan,
    taskset_argv,
)
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
    "NumaStatus",
    "LocalityPlan",
    "build_numa_bind_argv",
    "build_affinity_prefix",
    "collect_numa_status",
    "llama_numa_flag",
    "publish_numa_metrics",
    "resolve_locality_plan",
    "taskset_argv",
    "ThreadPinning",
    "TopologyService",
]
