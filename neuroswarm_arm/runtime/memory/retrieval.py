"""Retrieval orchestration — provider search + local filters + ranking."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.cache import MemoryCache
from neuroswarm_arm.runtime.memory.importance import ImportanceEngine
from neuroswarm_arm.runtime.memory.middleware import CircuitBreaker, with_retry
from neuroswarm_arm.runtime.memory.providers.base import IMemoryProvider
from neuroswarm_arm.runtime.memory.ranking import RankingEngine
from neuroswarm_arm.runtime.memory.schemas import SearchHit, SearchQuery
from neuroswarm_arm.runtime.memory.ttl import TTLManager
from neuroswarm_arm.runtime.memory.validators import validate_query


class RetrievalEngine:
    def __init__(
        self,
        provider: IMemoryProvider,
        *,
        ranking: RankingEngine | None = None,
        importance: ImportanceEngine | None = None,
        ttl: TTLManager | None = None,
        cache: MemoryCache[str, list[SearchHit]] | None = None,
        circuit: CircuitBreaker | None = None,
        retries: int = 2,
    ) -> None:
        self.provider = provider
        self.ranking = ranking or RankingEngine()
        self.importance = importance
        self.ttl = ttl
        self.cache = cache
        self.circuit = circuit
        self.retries = retries

    def _cache_key(self, query: SearchQuery) -> str:
        types = ",".join(t.value for t in (query.memory_types or []))
        return f"{query.owner}|{query.namespace}|{query.text}|{query.limit}|{types}"

    def retrieve(self, query: SearchQuery) -> list[SearchHit]:
        query = validate_query(query)
        key = self._cache_key(query)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        def _search() -> list[SearchHit]:
            return self.provider.search(query)

        hits = with_retry(_search, attempts=self.retries, circuit=self.circuit, label="search")
        live: list[SearchHit] = []
        for hit in hits:
            rec = hit.record
            if self.ttl is not None and self.ttl.expired(rec):
                continue
            if self.importance is not None:
                self.importance.rescore(rec)
            rec.touch()
            live.append(hit)
        ranked = self.ranking.fuse(live, time_decay=query.time_decay)
        if self.cache is not None:
            self.cache.set(key, ranked)
        return ranked
