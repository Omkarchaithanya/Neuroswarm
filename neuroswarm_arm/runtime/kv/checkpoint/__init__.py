"""Session checkpoint store — metadata separate from payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio

from ..interfaces.checkpoint import IKVCheckpointStore


class FileCheckpointStore(IKVCheckpointStore):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_")
        path = self.root / safe
        path.mkdir(parents=True, exist_ok=True)
        (path / "payloads").mkdir(parents=True, exist_ok=True)
        return path

    async def save_meta(self, session_id: str, meta: dict[str, Any]) -> None:
        path = self._session_dir(session_id) / "meta.json"

        def _write() -> None:
            path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

        await anyio.to_thread.run_sync(_write)

    async def load_meta(self, session_id: str) -> dict[str, Any]:
        path = self._session_dir(session_id) / "meta.json"

        def _read() -> dict[str, Any]:
            if not path.exists():
                raise KeyError(session_id)
            return json.loads(path.read_text(encoding="utf-8"))

        return await anyio.to_thread.run_sync(_read)

    async def save_payload(self, session_id: str, block_id: str, data: bytes) -> None:
        path = self._session_dir(session_id) / "payloads" / f"{block_id}.bin"

        def _write() -> None:
            path.write_bytes(data)

        await anyio.to_thread.run_sync(_write)

    async def load_payload(self, session_id: str, block_id: str) -> bytes:
        path = self._session_dir(session_id) / "payloads" / f"{block_id}.bin"

        def _read() -> bytes:
            if not path.exists():
                raise KeyError(f"{session_id}/{block_id}")
            return path.read_bytes()

        return await anyio.to_thread.run_sync(_read)

    async def delete_session(self, session_id: str) -> None:
        path = self._session_dir(session_id)

        def _delete() -> None:
            import shutil

            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

        await anyio.to_thread.run_sync(_delete)

    async def list_sessions(self) -> list[str]:
        def _list() -> list[str]:
            return sorted(p.name for p in self.root.iterdir() if p.is_dir() and (p / "meta.json").exists())

        return await anyio.to_thread.run_sync(_list)


class CheckpointEngine:
    """High-level checkpoint / restore helpers used by KVRuntimeManager."""

    def __init__(self, store: IKVCheckpointStore) -> None:
        self.store = store

    async def checkpoint(
        self,
        session_id: str,
        meta: dict[str, Any],
        payloads: dict[str, bytes],
    ) -> dict[str, Any]:
        for block_id, data in payloads.items():
            await self.store.save_payload(session_id, block_id, data)
        await self.store.save_meta(session_id, meta)
        return {"session_id": session_id, "blocks": len(payloads), "status": "ok"}

    async def restore(self, session_id: str) -> tuple[dict[str, Any], dict[str, bytes]]:
        meta = await self.store.load_meta(session_id)
        payloads: dict[str, bytes] = {}
        for block_id in meta.get("payload_ids", []):
            payloads[block_id] = await self.store.load_payload(session_id, block_id)
        return meta, payloads
