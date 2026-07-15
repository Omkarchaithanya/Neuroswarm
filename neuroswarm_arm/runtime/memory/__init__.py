"""Cognitive Memory Runtime — NEXUS Layer 4 episodic plane on top of Mem0.

Import ``NeuroMemory`` / ``Mem0Adapter`` / ``build_memory_runtime``.
Never import ``mem0ai`` outside ``neuroswarm_arm.runtime.memory.adapter``.
"""

from neuroswarm_arm.runtime.memory.adapter import Mem0Adapter
from neuroswarm_arm.runtime.memory.adapter.sdk_client import build_mem0_config
from neuroswarm_arm.runtime.memory.api import NeuroMemory
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig, load_memory_config
from neuroswarm_arm.runtime.memory.factory import build_mem0_adapter, build_memory_runtime
from neuroswarm_arm.runtime.memory.schemas import (
    MemoryRecord,
    MemoryType,
    PredictionResult,
    ReflectionResult,
    SearchHit,
    SearchQuery,
)
from neuroswarm_arm.runtime.memory.service import MemoryRuntime

__all__ = [
    "Mem0Adapter",
    "NeuroMemory",
    "MemoryRuntime",
    "MemoryRuntimeConfig",
    "MemoryRecord",
    "MemoryType",
    "SearchQuery",
    "SearchHit",
    "ReflectionResult",
    "PredictionResult",
    "build_memory_runtime",
    "build_mem0_adapter",
    "build_mem0_config",
    "load_memory_config",
]
