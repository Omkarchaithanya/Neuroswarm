"""DIPA routing package — scored model/backend/topology selection."""

from __future__ import annotations

from .backend_selector import BackendSelector
from .cpu_affinity_router import CpuAffinityRouter
from .decode_router import DecodeRoute, DecodeRouter
from .model_router import ModelRouter
from .numa_router import NumaRouter
from .prefill_router import PrefillRoute, PrefillRouter
from .quant_router import QuantRouter
from .speculation_router import SpeculationRouter
from .topology_router import TopologyRouter

__all__ = [
    "BackendSelector",
    "CpuAffinityRouter",
    "DecodeRoute",
    "DecodeRouter",
    "ModelRouter",
    "NumaRouter",
    "PrefillRoute",
    "PrefillRouter",
    "QuantRouter",
    "SpeculationRouter",
    "TopologyRouter",
]
