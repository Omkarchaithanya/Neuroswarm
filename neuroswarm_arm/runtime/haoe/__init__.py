"""HAOE — Heterogeneous Agentic Orchestration Engine (Layer 1 / Plane 4).

The agent runtime kernel for NEXUS-ARM. Everything executes through HAOE.
HAOE coordinates inference; it never performs inference.
"""

from __future__ import annotations

from .factory import build_haoe
from .kernel import HAOERuntime, HAOEScheduler
from .runtime.runtime_config import HAOERuntimeConfig, load_haoe_config

__all__ = [
    "build_haoe",
    "HAOERuntime",
    "HAOEScheduler",
    "HAOERuntimeConfig",
    "load_haoe_config",
]
