"""NVMe backend — cold cache, paging, async load, compression-ready."""

from __future__ import annotations

from pathlib import Path

from neuroswarm_arm.runtime.kv.providers.nvme import NVMeProvider

from ..interfaces import ICompression
from ..models import ProviderStats
from ._adapter import Plane2ProviderAdapter


class NVMeBackend(Plane2ProviderAdapter):
    def __init__(self, root: Path, compression: ICompression | None = None) -> None:
        super().__init__(NVMeProvider(Path(root) / "nvme"), name="nvme")
        self.root = Path(root)
        self.compression = compression

    async def store(self, kv_id: str, data: bytes) -> None:
        payload = self.compression.compress(data) if self.compression is not None else data
        await super().store(kv_id, payload)

    async def load(self, kv_id: str) -> bytes:
        data = await super().load(kv_id)
        if self.compression is not None:
            return self.compression.decompress(data)
        return data

    async def stats(self) -> ProviderStats:
        st = await super().stats()
        st.extra["compression"] = self.compression.name if self.compression else "none"
        return st


def build_nvme_backend(root: Path, compression: ICompression | None = None) -> NVMeBackend:
    return NVMeBackend(root, compression=compression)
