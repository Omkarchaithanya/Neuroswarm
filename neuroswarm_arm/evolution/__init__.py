"""Plane 5 — Autonomic Runtime Optimization Plane (AROP).

NEXUS Layer 5 remains MAKS. AROP is the Evolution / Plane 5 optimizer:
Performix is an ObservationProvider; GEPA is a ReflectionStrategy;
all runtime changes flow through policy generation → experiment →
validation → safety → canary → rollback → knowledge update.
"""

from __future__ import annotations

from .config import AROPConfig, load_arop_config
from .factory import AROPRuntime, build_arop
from .performix_client import PerformixClient
from .runtime_optimizer import PipelineResult, RuntimeOptimizer

# Backward-compatible EvolutionLoop shim
from .evolution_loop import EvolutionLoop

__all__ = [
    "AROPConfig",
    "AROPRuntime",
    "EvolutionLoop",
    "PerformixClient",
    "PipelineResult",
    "RuntimeOptimizer",
    "build_arop",
    "load_arop_config",
]
