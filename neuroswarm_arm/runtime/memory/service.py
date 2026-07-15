"""MemoryRuntime — core orchestrator (provider-agnostic)."""

from __future__ import annotations

import random
from typing import Any

from neuroswarm_arm.runtime.memory.cache import MemoryCache
from neuroswarm_arm.runtime.memory.compression import CompressionEngine
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.exceptions import MemoryNotFoundError
from neuroswarm_arm.runtime.memory.graph import MemoryGraph
from neuroswarm_arm.runtime.memory.health import MemoryHealth
from neuroswarm_arm.runtime.memory.history import HistoryIndex
from neuroswarm_arm.runtime.memory.importance import ImportanceEngine
from neuroswarm_arm.runtime.memory.logging import log_event
from neuroswarm_arm.runtime.memory.metrics import MemoryMetrics
from neuroswarm_arm.runtime.memory.middleware import CircuitBreaker, with_retry
from neuroswarm_arm.runtime.memory.namespace import namespace_for_type, normalize_namespace
from neuroswarm_arm.runtime.memory.policies import LifecyclePolicy
from neuroswarm_arm.runtime.memory.predictor import Predictor
from neuroswarm_arm.runtime.memory.providers.base import IMemoryProvider
from neuroswarm_arm.runtime.memory.ranking import RankingEngine
from neuroswarm_arm.runtime.memory.reflection import ReflectionEngine
from neuroswarm_arm.runtime.memory.relationships import RelationshipManager
from neuroswarm_arm.runtime.memory.retrieval import RetrievalEngine
from neuroswarm_arm.runtime.memory.schemas import (
    MemoryRecord,
    MemoryType,
    PredictionResult,
    ReflectionResult,
    SearchHit,
    SearchQuery,
)
from neuroswarm_arm.runtime.memory.summarizer import Summarizer
from neuroswarm_arm.runtime.memory.ttl import TTLManager
from neuroswarm_arm.runtime.memory.validators import validate_record


class MemoryRuntime:
    def __init__(
        self,
        provider: IMemoryProvider,
        config: MemoryRuntimeConfig,
        *,
        fallback: IMemoryProvider | None = None,
        metrics: MemoryMetrics | None = None,
    ) -> None:
        self.provider = provider
        self.fallback = fallback
        self.config = config
        self.metrics = metrics or MemoryMetrics()
        self.circuit = CircuitBreaker(
            fail_threshold=config.circuit_fail_threshold,
            reset_seconds=config.circuit_reset_seconds,
        )
        self.policy = LifecyclePolicy(config)
        self.importance = ImportanceEngine(config)
        self.ttl = TTLManager(self.policy)
        self.cache: MemoryCache[str, list[SearchHit]] = MemoryCache(
            max_entries=config.cache_max_entries,
            ttl_seconds=float(config.cache_ttl_seconds),
        )
        self.ranking = RankingEngine()
        self.retrieval = RetrievalEngine(
            provider,
            ranking=self.ranking,
            importance=self.importance,
            ttl=self.ttl,
            cache=self.cache,
            circuit=self.circuit,
            retries=config.retry_attempts,
        )
        self.reflection = ReflectionEngine()
        self.summarizer = Summarizer()
        self.compression = CompressionEngine(self.summarizer)
        self.predictor = Predictor()
        self.relationships = RelationshipManager()
        self.graph = MemoryGraph()
        self.history = HistoryIndex(config.metadata_index_path or config.store_root / "index" / "metadata.json")
        self.health = MemoryHealth(provider, secondary=fallback)

    def _active_provider(self) -> IMemoryProvider:
        if self.circuit.open and self.fallback is not None:
            return self.fallback
        return self.provider

    def remember(self, record: MemoryRecord) -> MemoryRecord:
        record.namespace = record.namespace or namespace_for_type(record.type)
        record = self.policy.apply_defaults(record)
        record = validate_record(record)
        self.importance.rescore(record)
        self.summarizer.summarize_record(record)

        def _add() -> MemoryRecord:
            return self._active_provider().add(record)

        with self.metrics.timed("remember_latency"):
            try:
                saved = with_retry(
                    _add,
                    attempts=self.config.retry_attempts,
                    circuit=self.circuit,
                    label="remember",
                )
            except Exception:
                if self.fallback is not None and self._active_provider() is not self.fallback:
                    saved = self.fallback.add(record)
                    log_event("remember_fallback", uuid=record.uuid)
                else:
                    raise
        self.history.upsert(saved)
        self.graph.index(saved)
        self.cache.invalidate()
        self.metrics.inc("remember_total")
        self.metrics.inc(f"remember_type_{saved.type.value}")
        return saved

    def remember_typed(
        self,
        content: str,
        memory_type: MemoryType,
        *,
        owner: str = "default",
        **kwargs: Any,
    ) -> MemoryRecord:
        ns = kwargs.pop("namespace", None) or namespace_for_type(memory_type)
        record = MemoryRecord(
            content=content,
            type=memory_type,
            namespace=normalize_namespace(ns),
            owner=owner,
            **kwargs,
        )
        return self.remember(record)

    def search(self, query: SearchQuery | str, *, owner: str = "default", **kwargs: Any) -> list[SearchHit]:
        if isinstance(query, str):
            query = SearchQuery(text=query, owner=owner, **kwargs)
        with self.metrics.timed("retrieval_latency"):
            hits = self.retrieval.retrieve(query)
        self.metrics.inc("search_total")
        self.metrics.set_gauge("cache_hit_rate", self.cache.hit_rate)
        return hits

    def recall(self, owner: str, query: str, *, limit: int = 5, namespace: str | None = None) -> list[str]:
        hits = self.search(SearchQuery(text=query, owner=owner, limit=limit, namespace=namespace))
        return [h.record.content for h in hits]

    def retrieve(self, query: SearchQuery) -> list[MemoryRecord]:
        return [h.record for h in self.search(query)]

    def get(self, memory_id: str) -> MemoryRecord:
        rec = self._active_provider().get(memory_id)
        if rec is None and self.fallback is not None:
            rec = self.fallback.get(memory_id)
        if rec is None:
            raise MemoryNotFoundError(memory_id)
        return rec

    def archive(self, memory_id: str) -> MemoryRecord:
        rec = self.get(memory_id)
        rec.archived = True
        self.history.mark_archived(memory_id)
        # ADD-only: write archived marker fact
        marker = MemoryRecord(
            content=f"archived:{memory_id}",
            type=MemoryType.SYSTEM,
            namespace="system/",
            owner=rec.owner,
            metadata={"archived_id": memory_id},
            tags=["archive"],
        )
        self.remember(marker)
        self.metrics.inc("archive_total")
        return rec

    def forget(self, memory_id: str) -> bool:
        ok = self._active_provider().delete(memory_id)
        if not ok and self.fallback is not None:
            ok = self.fallback.delete(memory_id)
        self.cache.invalidate()
        self.metrics.inc("forget_total")
        return ok

    def compress(self, owner: str, *, keep: int = 100) -> list[MemoryRecord]:
        with self.metrics.timed("compression_latency"):
            ids = self._active_provider().list_ids(owner=owner)
            records = [r for mid in ids if (r := self._active_provider().get(mid)) is not None]
            for a, b in self.compression.find_duplicates(records):
                merged = self.compression.merge(a, b)
                self.remember(merged)
                self.forget(b.uuid)
            kept = self.compression.prune(records, keep=keep)
        self.metrics.inc("compress_total")
        return kept

    def summarize(self, memory_id: str) -> str:
        rec = self.get(memory_id)
        self.summarizer.summarize_record(rec)
        return rec.summary

    def predict_next(self, owner: str, *, context: str = "") -> PredictionResult:
        if not self.config.enable_prediction:
            return PredictionResult()
        hits = self.search(SearchQuery(text=context or "predict", owner=owner, limit=50))
        return self.predictor.predict([h.record for h in hits], context=context)

    def reflect(
        self,
        *,
        owner: str,
        workflow_id: str = "",
        success: bool = True,
        failures: list[str] | None = None,
        tools_used: list[str] | None = None,
        notes: str = "",
        latency_ms: float = 0.0,
        cost: float = 0.0,
        origin_agent: str = "",
    ) -> ReflectionResult:
        if not self.config.enable_reflection:
            return ReflectionResult()
        with self.metrics.timed("reflection_latency"):
            result = self.reflection.reflect(
                workflow_id=workflow_id,
                success=success,
                failures=failures,
                tools_used=tools_used,
                notes=notes,
                latency_ms=latency_ms,
                cost=cost,
            )
            for rec in self.reflection.to_records(
                result, owner=owner, workflow_id=workflow_id, origin_agent=origin_agent
            ):
                saved = self.remember(rec)
                result.memory_ids.append(saved.uuid)
        self.metrics.inc("reflect_total")
        return result

    def rank(self, hits: list[SearchHit]) -> list[SearchHit]:
        with self.metrics.timed("ranking_latency"):
            return self.ranking.fuse(hits)

    def promote(self, memory_id: str) -> MemoryRecord:
        rec = self.get(memory_id)
        rec.importance = min(1.0, max(rec.importance, self.policy.promote_importance_above))
        rec.tags = list({*rec.tags, "promoted"})
        return self.remember(rec)

    def demote(self, memory_id: str) -> MemoryRecord:
        rec = self.get(memory_id)
        rec.importance = min(rec.importance, self.policy.demote_importance_below)
        rec.tags = list({*rec.tags, "demoted"})
        return self.remember(rec)

    def link(self, a_id: str, b_id: str, *, rel: str = "related") -> None:
        a = self.get(a_id)
        b = self.get(b_id)
        self.relationships.link(a, b, rel=rel)
        self.graph.index(a)
        self.graph.index(b)
        self.history.upsert(a)
        self.history.upsert(b)

    def merge(self, a_id: str, b_id: str) -> MemoryRecord:
        a = self.get(a_id)
        b = self.get(b_id)
        merged = self.compression.merge(a, b)
        saved = self.remember(merged)
        self.forget(b_id)
        return saved

    def should_sample_performance(self) -> bool:
        return random.random() <= self.config.sample_performance

    def health_check(self):
        status = self.health.check()
        self.metrics.set_gauge("healthy", 1.0 if status.healthy else 0.0)
        return status
