"""DIPA — Disaggregated Inference Proxy for Agents (Layer 2 / Plane 3).

Inference Runtime Kernel for NEXUS-ARM. Every inference decision flows through
DIPA. HAOE coordinates agents; DIPA owns backends, cascade, quant/warm/KV asks.
"""

from __future__ import annotations

from .factory import build_dipa
from .kernel import DIPARuntime, RuntimeManager
from .engine_adapter import InferenceEngineAdapter
from .runtime.runtime_config import DIPARuntimeConfig, load_dipa_config

__all__ = [
    "DIPARuntime",
    "DIPARuntimeConfig",
    "InferenceEngineAdapter",
    "RuntimeManager",
    "build_dipa",
    "load_dipa_config",
]
