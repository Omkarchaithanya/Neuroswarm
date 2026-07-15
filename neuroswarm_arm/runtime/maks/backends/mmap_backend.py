"""mmap backend — memory-mapped files for large contexts / persistent reuse."""

from __future__ import annotations

from pathlib import Path

from neuroswarm_arm.runtime.kv.providers.mmap_provider import MemoryMappedProvider

from ._adapter import Plane2ProviderAdapter


class MMapBackend(Plane2ProviderAdapter):
    def __init__(self, root: Path) -> None:
        super().__init__(MemoryMappedProvider(Path(root) / "mmap"), name="mmap")
        self.root = Path(root)


def build_mmap_backend(root: Path) -> MMapBackend:
    return MMapBackend(root)
