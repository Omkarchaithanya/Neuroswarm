"""LMDB provider (L4)."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

import anyio

from ..interfaces.provider import IKVProvider
from ..interfaces.types import StorageTier


class LMDBProvider(IKVProvider):
    def __init__(self, root: Path, map_size: int = 1 << 30) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._map_size = map_size
        self._lock = RLock()
        self._env = None
        self._bytes = 0
        self._open()

    def _open(self) -> None:
        try:
            import lmdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("lmdb package required; pip install lmdb") from exc
        self._env = lmdb.open(
            str(self.root / "kv.lmdb"),
            map_size=self._map_size,
            max_dbs=1,
            writemap=True,
            metasync=False,
            sync=False,
        )
        with self._env.begin() as txn:
            self._bytes = int(txn.stat()["psize"] * txn.stat().get("leaf_pages", 0))

    @property
    def name(self) -> str:
        return "lmdb"

    @property
    def tier(self) -> StorageTier:
        return StorageTier.L4_LMDB

    async def put(self, key: str, data: bytes) -> None:
        def _write() -> None:
            assert self._env is not None
            with self._lock:
                with self._env.begin(write=True) as txn:
                    old = txn.get(key.encode("utf-8"))
                    if old is not None:
                        self._bytes -= len(old)
                    txn.put(key.encode("utf-8"), data)
                    self._bytes += len(data)

        await anyio.to_thread.run_sync(_write)

    async def get(self, key: str) -> bytes:
        def _read() -> bytes:
            assert self._env is not None
            with self._lock:
                with self._env.begin() as txn:
                    val = txn.get(key.encode("utf-8"))
                    if val is None:
                        raise KeyError(key)
                    return bytes(val)

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            assert self._env is not None
            with self._lock:
                with self._env.begin(write=True) as txn:
                    old = txn.get(key.encode("utf-8"))
                    if old is not None:
                        self._bytes -= len(old)
                        txn.delete(key.encode("utf-8"))

        await anyio.to_thread.run_sync(_delete)

    async def exists(self, key: str) -> bool:
        def _exists() -> bool:
            assert self._env is not None
            with self._lock:
                with self._env.begin() as txn:
                    return txn.get(key.encode("utf-8")) is not None

        return await anyio.to_thread.run_sync(_exists)

    def usage_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def close(self) -> None:
        if self._env is not None:
            self._env.close()
            self._env = None
