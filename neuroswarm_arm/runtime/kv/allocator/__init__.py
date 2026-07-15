"""NUMA-aware allocators with Axion single-node fallback."""

from __future__ import annotations

from .numa import NUMAPlacementPolicy, LocalRAMAllocator, detect_numa_nodes

__all__ = ["LocalRAMAllocator", "NUMAPlacementPolicy", "detect_numa_nodes"]
