"""LMDB sharing backend."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

import anyio

from ..interfaces.sharing import IKVSharingBackend


class LMDBSharingBackend(IKVSharingBackend):
    def __init__(self, root: Path, map_size: int = 1 << 28) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        try:
            import lmdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("lmdb package required") from exc
        self._env = lmdb.open(str(self.root / "share.lmdb"), map_size=map_size)

    @property
    def name(self) -> str:
        return "lmdb"

    def _meta_key(self, key: str) -> bytes:
        return f"meta:{key}".encode("utf-8")

    def _data_key(self, key: str) -> bytes:
        return f"data:{key}".encode("utf-8")

    async def store(self, key: str, data: bytes) -> None:
        def _write() -> None:
            with self._lock:
                with self._env.begin(write=True) as txn:
                    txn.put(self._data_key(key), data)
                    txn.put(
                        self._meta_key(key),
                        json.dumps({"refcount": 1, "consumers": []}).encode("utf-8"),
                    )

        await anyio.to_thread.run_sync(_write)

    async def load(self, key: str) -> bytes:
        def _read() -> bytes:
            with self._lock:
                with self._env.begin() as txn:
                    val = txn.get(self._data_key(key))
                    if val is None:
                        raise KeyError(key)
                    return bytes(val)

        return await anyio.to_thread.run_sync(_read)

    async def share(self, key: str, consumer_id: str) -> str:
        def _share() -> str:
            with self._lock:
                with self._env.begin(write=True) as txn:
                    raw = txn.get(self._meta_key(key))
                    if raw is None:
                        raise KeyError(key)
                    meta = json.loads(raw.decode("utf-8"))
                    meta["refcount"] = int(meta.get("refcount", 1)) + 1
                    consumers = list(meta.get("consumers", []))
                    if consumer_id not in consumers:
                        consumers.append(consumer_id)
                    meta["consumers"] = consumers
                    txn.put(self._meta_key(key), json.dumps(meta).encode("utf-8"))
                    return f"share:{key}:{consumer_id}"

        return await anyio.to_thread.run_sync(_share)

    async def release(self, key: str, consumer_id: str) -> None:
        def _release() -> None:
            with self._lock:
                with self._env.begin(write=True) as txn:
                    raw = txn.get(self._meta_key(key))
                    if raw is None:
                        return
                    meta = json.loads(raw.decode("utf-8"))
                    consumers = [c for c in meta.get("consumers", []) if c != consumer_id]
                    meta["consumers"] = consumers
                    meta["refcount"] = max(0, int(meta.get("refcount", 1)) - 1)
                    if meta["refcount"] <= 0:
                        txn.delete(self._meta_key(key))
                        txn.delete(self._data_key(key))
                    else:
                        txn.put(self._meta_key(key), json.dumps(meta).encode("utf-8"))

        await anyio.to_thread.run_sync(_release)

    async def reference_count(self, key: str) -> int:
        def _rc() -> int:
            with self._lock:
                with self._env.begin() as txn:
                    raw = txn.get(self._meta_key(key))
                    if raw is None:
                        return 0
                    return int(json.loads(raw.decode("utf-8")).get("refcount", 0))

        return await anyio.to_thread.run_sync(_rc)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            with self._lock:
                with self._env.begin(write=True) as txn:
                    txn.delete(self._meta_key(key))
                    txn.delete(self._data_key(key))

        await anyio.to_thread.run_sync(_delete)
