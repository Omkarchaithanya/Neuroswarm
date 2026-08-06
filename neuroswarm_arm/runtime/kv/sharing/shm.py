"""In-process / shared-memory sharing backend."""

from __future__ import annotations

import os
import re
from multiprocessing import shared_memory
from threading import RLock
from typing import Any

import anyio

from ..interfaces.sharing import IKVSharingBackend
from ..utils.hashing import stable_id
from ..utils.locks import RefCountedLock


class SharedMemoryBackend(IKVSharingBackend):
    """Uses multiprocessing.shared_memory when available; falls back to process RAM."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._meta: dict[str, dict[str, Any]] = {}
        self._fallback: dict[str, bytes] = {}
        self._refs: dict[str, RefCountedLock] = {}
        self._consumers: dict[str, set[str]] = {}

    @property
    def name(self) -> str:
        return "shm"

    async def store(self, key: str, data: bytes) -> None:
        def _store() -> None:
            with self._lock:
                self._cleanup_key(key)
                name = f"nsa_kv_{stable_id('shm')}"
                try:
                    shm = shared_memory.SharedMemory(create=True, size=max(1, len(data)), name=name)
                    shm.buf[: len(data)] = data
                    self._meta[key] = {"name": name, "size": len(data), "shm": shm}
                except Exception:
                    self._fallback[key] = data
                    self._meta[key] = {"name": None, "size": len(data), "shm": None}
                self._refs[key] = RefCountedLock(1)
                self._consumers[key] = set()

        await anyio.to_thread.run_sync(_store)

    async def load(self, key: str) -> bytes:
        def _load() -> bytes:
            with self._lock:
                if key not in self._meta:
                    raise KeyError(key)
                meta = self._meta[key]
                shm = meta.get("shm")
                if shm is not None:
                    return bytes(shm.buf[: meta["size"]])
                if key in self._fallback:
                    return self._fallback[key]
                raise KeyError(key)

        return await anyio.to_thread.run_sync(_load)

    async def share(self, key: str, consumer_id: str) -> str:
        with self._lock:
            if key not in self._refs:
                raise KeyError(key)
            self._refs[key].acquire_ref()
            self._consumers.setdefault(key, set()).add(consumer_id)
            return f"share:{key}:{consumer_id}"

    async def release(self, key: str, consumer_id: str) -> None:
        with self._lock:
            if key not in self._refs:
                return
            self._consumers.get(key, set()).discard(consumer_id)
            remaining = self._refs[key].release_ref()
            if remaining == 0:
                self._cleanup_key(key)

    async def reference_count(self, key: str) -> int:
        with self._lock:
            if key not in self._refs:
                return 0
            return self._refs[key].count

    async def delete(self, key: str) -> None:
        with self._lock:
            self._cleanup_key(key)

    def _cleanup_key(self, key: str) -> None:
        meta = self._meta.pop(key, None)
        self._fallback.pop(key, None)
        self._refs.pop(key, None)
        self._consumers.pop(key, None)
        if meta and meta.get("shm") is not None:
            shm = meta["shm"]
            try:
                shm.close()
                # Only unlink when ref count hits 0
                shm.unlink()
            except Exception:
                pass

    def create_named_region(self, name: str, size: int) -> shared_memory.SharedMemory:
        """
        Create a new named shared memory region.

        Args:
            name: Name of the SHM segment (e.g., "nsa_kv_session123")
            size: Size in bytes (including metadata header)

        Returns:
            SharedMemory object (caller must manage close/unlink)
        """
        with self._lock:
            # Clean up any existing with same name
            try:
                existing = shared_memory.SharedMemory(name=name)
                existing.close()
                existing.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass

            shm = shared_memory.SharedMemory(create=True, size=max(1, size), name=name)
            self._meta[name] = {"name": name, "size": size, "shm": shm, "refcount": 1}
            self._refs[name] = RefCountedLock(1)
            return shm

    def attach_named_region(self, name: str) -> shared_memory.SharedMemory:
        """
        Attach to an existing named shared memory region (no create=True).

        Args:
            name: Name of the existing SHM segment

        Returns:
            SharedMemory object attached to the existing region
        """
        with self._lock:
            shm = shared_memory.SharedMemory(name=name)
            if name not in self._meta:
                self._meta[name] = {"name": name, "size": len(shm.buf), "shm": shm, "refcount": 0}
                self._refs[name] = RefCountedLock(0)
            self._refs[name].acquire_ref()
            self._meta[name]["refcount"] = self._refs[name].count
            return shm

    def get_fd(self, name: str) -> int:
        """
        Get the file descriptor for a named SHM region by reading /proc/self/map_files/.

        Used for passing SHM fd to child processes (e.g., llama-server).

        Args:
            name: Name of the SHM segment

        Returns:
            File descriptor integer

        Raises:
            FileNotFoundError: If SHM region not found in map_files
        """
        # The SHM file appears in /dev/shm/ but we need the fd from map_files
        # /proc/self/map_files/ contains symlinks like:
        # 7f1234567000-7f1234568000 -> /dev/shm/nsa_kv_session123
        pattern = re.compile(rf".*{re.escape(name)}$")
        try:
            for entry in os.listdir("/proc/self/map_files/"):
                if pattern.match(entry):
                    # entry is like "7f1234567000-7f1234568000"
                    # The symlink target is /dev/shm/name
                    link_path = os.path.join("/proc/self/map_files/", entry)
                    target = os.readlink(link_path)
                    if target.endswith(name):
                        # Open the SHM file to get fd
                        fd = os.open(target, os.O_RDWR)
                        return fd
        except (FileNotFoundError, PermissionError, OSError):
            pass
        raise FileNotFoundError(f"SHM region '{name}' not found in /proc/self/map_files/")

    def release_region(self, name: str) -> None:
        """
        Release a named SHM region (decrement refcount, cleanup when 0).

        Args:
            name: Name of the SHM segment
        """
        with self._lock:
            if name not in self._refs:
                return
            remaining = self._refs[name].release_ref()
            if name in self._meta:
                self._meta[name]["refcount"] = remaining
            if remaining <= 0:
                self._cleanup_key(name)
