"""SQLite-backed registry persistence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

import anyio

from ..interfaces import IRegistryStore
from ..models import KVRegistryRecord


class SQLiteRegistryStore(IRegistryStore):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv_registry (
                        kv_id TEXT PRIMARY KEY,
                        dedup_key TEXT,
                        prompt_hash TEXT,
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_dedup ON kv_registry(dedup_key)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_prompt ON kv_registry(prompt_hash)"
                )
                conn.commit()
            finally:
                conn.close()

    async def put(self, record: KVRegistryRecord) -> None:
        payload = record.model_dump_json()

        def _write() -> None:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        INSERT INTO kv_registry(kv_id, dedup_key, prompt_hash, payload)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(kv_id) DO UPDATE SET
                            dedup_key=excluded.dedup_key,
                            prompt_hash=excluded.prompt_hash,
                            payload=excluded.payload
                        """,
                        (record.kv_id, record.dedup_key, record.prompt_hash, payload),
                    )
                    conn.commit()
                finally:
                    conn.close()

        await anyio.to_thread.run_sync(_write)

    async def get(self, kv_id: str) -> KVRegistryRecord | None:
        def _read() -> KVRegistryRecord | None:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT payload FROM kv_registry WHERE kv_id=?",
                        (kv_id,),
                    ).fetchone()
                    if row is None:
                        return None
                    return KVRegistryRecord.model_validate_json(row[0])
                finally:
                    conn.close()

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, kv_id: str) -> None:
        def _del() -> None:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM kv_registry WHERE kv_id=?", (kv_id,))
                    conn.commit()
                finally:
                    conn.close()

        await anyio.to_thread.run_sync(_del)

    async def list_ids(self) -> list[str]:
        def _list() -> list[str]:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute("SELECT kv_id FROM kv_registry").fetchall()
                    return [r[0] for r in rows]
                finally:
                    conn.close()

        return await anyio.to_thread.run_sync(_list)

    async def find_by_dedup(self, dedup_key: str) -> KVRegistryRecord | None:
        def _find() -> KVRegistryRecord | None:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT payload FROM kv_registry WHERE dedup_key=? LIMIT 1",
                        (dedup_key,),
                    ).fetchone()
                    if row is None:
                        return None
                    return KVRegistryRecord.model_validate_json(row[0])
                finally:
                    conn.close()

        return await anyio.to_thread.run_sync(_find)

    async def find_by_prefix(self, prompt_hash: str) -> list[KVRegistryRecord]:
        def _find() -> list[KVRegistryRecord]:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        "SELECT payload FROM kv_registry WHERE prompt_hash=? OR prompt_hash LIKE ?",
                        (prompt_hash, f"{prompt_hash}%"),
                    ).fetchall()
                    return [KVRegistryRecord.model_validate_json(r[0]) for r in rows]
                finally:
                    conn.close()

        return await anyio.to_thread.run_sync(_find)
