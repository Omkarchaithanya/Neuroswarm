"""Redis-backed registry persistence (distributed refcount / lookup)."""

from __future__ import annotations

from threading import RLock

import anyio

from ..exceptions import KVRegistryError
from ..interfaces import IRegistryStore
from ..models import KVRegistryRecord


class RedisRegistryStore(IRegistryStore):
    def __init__(self, url: str = "redis://localhost:6379/0", *, prefix: str = "maks:reg:") -> None:
        self.url = url
        self.prefix = prefix
        self._lock = RLock()
        self._client = None
        self._available = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
        except ImportError:
            return
        try:
            client = redis.Redis.from_url(self.url, decode_responses=True)
            client.ping()
            self._client = client
            self._available = True
        except Exception:
            self._client = None
            self._available = False

    def _require(self):
        if not self._available or self._client is None:
            raise KVRegistryError("Redis registry unavailable")
        return self._client

    def _key(self, kv_id: str) -> str:
        return f"{self.prefix}{kv_id}"

    def _dedup_key(self, dedup_key: str) -> str:
        return f"{self.prefix}dedup:{dedup_key}"

    def _prompt_key(self, prompt_hash: str) -> str:
        return f"{self.prefix}prompt:{prompt_hash}"

    async def put(self, record: KVRegistryRecord) -> None:
        def _write() -> None:
            with self._lock:
                client = self._require()
                payload = record.model_dump_json()
                pipe = client.pipeline()
                pipe.set(self._key(record.kv_id), payload)
                pipe.sadd(f"{self.prefix}ids", record.kv_id)
                if record.dedup_key:
                    pipe.set(self._dedup_key(record.dedup_key), record.kv_id)
                if record.prompt_hash:
                    pipe.sadd(self._prompt_key(record.prompt_hash), record.kv_id)
                pipe.execute()

        await anyio.to_thread.run_sync(_write)

    async def get(self, kv_id: str) -> KVRegistryRecord | None:
        def _read() -> KVRegistryRecord | None:
            with self._lock:
                client = self._require()
                raw = client.get(self._key(kv_id))
                if raw is None:
                    return None
                return KVRegistryRecord.model_validate_json(raw)

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, kv_id: str) -> None:
        def _del() -> None:
            with self._lock:
                client = self._require()
                raw = client.get(self._key(kv_id))
                pipe = client.pipeline()
                if raw:
                    rec = KVRegistryRecord.model_validate_json(raw)
                    if rec.dedup_key:
                        pipe.delete(self._dedup_key(rec.dedup_key))
                    if rec.prompt_hash:
                        pipe.srem(self._prompt_key(rec.prompt_hash), kv_id)
                pipe.delete(self._key(kv_id))
                pipe.srem(f"{self.prefix}ids", kv_id)
                pipe.execute()

        await anyio.to_thread.run_sync(_del)

    async def list_ids(self) -> list[str]:
        def _list() -> list[str]:
            with self._lock:
                client = self._require()
                return sorted(client.smembers(f"{self.prefix}ids") or [])

        return await anyio.to_thread.run_sync(_list)

    async def find_by_dedup(self, dedup_key: str) -> KVRegistryRecord | None:
        def _find() -> KVRegistryRecord | None:
            with self._lock:
                client = self._require()
                kv_id = client.get(self._dedup_key(dedup_key))
                if not kv_id:
                    return None
                raw = client.get(self._key(kv_id))
                if raw is None:
                    return None
                return KVRegistryRecord.model_validate_json(raw)

        return await anyio.to_thread.run_sync(_find)

    async def find_by_prefix(self, prompt_hash: str) -> list[KVRegistryRecord]:
        def _find() -> list[KVRegistryRecord]:
            with self._lock:
                client = self._require()
                ids = client.smembers(self._prompt_key(prompt_hash)) or set()
                out: list[KVRegistryRecord] = []
                for kv_id in ids:
                    raw = client.get(self._key(kv_id))
                    if raw:
                        out.append(KVRegistryRecord.model_validate_json(raw))
                return out

        return await anyio.to_thread.run_sync(_find)

    @property
    def available(self) -> bool:
        return self._available
