"""Mem0Provider — IMemoryProvider backed by Mem0 OSS v3."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from neuroswarm_arm.runtime.memory.adapter.sdk_client import Mem0Client, Mem0SdkClient
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.exceptions import MemoryProviderError
from neuroswarm_arm.runtime.memory.namespace import normalize_namespace
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, MemoryType, SearchHit, SearchQuery


def _parse_mem0_item(item: dict[str, Any], *, owner: str, namespace: str) -> MemoryRecord:
    mem_id = str(item.get("id") or item.get("memory_id") or uuid4())
    content = str(item.get("memory") or item.get("text") or item.get("data") or "")
    meta = dict(item.get("metadata") or {})
    mem_type_raw = meta.get("memory_type", MemoryType.FACT.value)
    try:
        mem_type = MemoryType(str(mem_type_raw))
    except ValueError:
        mem_type = MemoryType.FACT
    created = item.get("created_at") or item.get("updated_at")
    ts = datetime.now(timezone.utc)
    if isinstance(created, str):
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            pass
    return MemoryRecord(
        uuid=mem_id,
        content=content,
        type=mem_type,
        namespace=normalize_namespace(meta.get("namespace", namespace)),
        owner=owner,
        timestamp=ts,
        importance=float(meta.get("importance", 0.5)),
        confidence=float(meta.get("confidence", item.get("score", 0.8) or 0.8)),
        metadata=meta,
        tags=list(meta.get("tags") or item.get("categories") or []),
        origin_agent=str(meta.get("origin_agent") or item.get("agent_id") or ""),
        workflow_id=str(meta.get("workflow_id") or ""),
        execution_id=str(meta.get("execution_id") or ""),
        provider_id=mem_id,
        source="mem0",
        summary=str(meta.get("summary") or ""),
        cost=float(meta.get("cost", 0.0)),
        latency=float(meta.get("latency", 0.0)),
        success_score=float(meta.get("success_score", 0.0)),
        failure_reason=str(meta.get("failure_reason") or ""),
    )


class Mem0Provider:
    name = "mem0"

    def __init__(self, cfg: MemoryRuntimeConfig, client: Mem0Client | None = None) -> None:
        self.cfg = cfg
        self.client = client or Mem0Client(cfg)
        if not self.client.available:
            raise MemoryProviderError(f"Mem0Provider init failed: {self.client.health().get('error')}")

    def add(self, record: MemoryRecord) -> MemoryRecord:
        meta = {
            **record.metadata,
            "memory_type": record.type.value,
            "namespace": record.namespace,
            "importance": record.importance,
            "confidence": record.confidence,
            "tags": record.tags,
            "origin_agent": record.origin_agent,
            "workflow_id": record.workflow_id,
            "execution_id": record.execution_id,
            "uuid": record.uuid,
            "summary": record.summary,
            "cost": record.cost,
            "latency": record.latency,
            "success_score": record.success_score,
            "failure_reason": record.failure_reason,
        }
        # Direct fact ingest as message string (ADD-only; no UPDATE path)
        result = self.client.add(
            record.content,
            user_id=record.owner,
            agent_id=record.origin_agent or None,
            run_id=record.execution_id or None,
            metadata=meta,
        )
        # Capture provider ids when returned
        if isinstance(result, dict):
            results = result.get("results") or result.get("memories") or []
            if results and isinstance(results[0], dict):
                pid = results[0].get("id") or results[0].get("memory_id")
                if pid:
                    record.provider_id = str(pid)
        record.source = "mem0"
        return record

    def add_messages(
        self,
        messages: str | list[dict[str, str]],
        *,
        owner: str,
        agent_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        if self.cfg.llm_mode == "none":
            # Bypass extraction LLM — store raw text
            text = messages if isinstance(messages, str) else "\n".join(
                f"{m.get('role')}: {m.get('content')}" for m in messages
            )
            rec = MemoryRecord(
                content=text,
                owner=owner,
                origin_agent=agent_id or owner,
                execution_id=run_id,
                metadata=metadata or {},
                namespace="agents/",
            )
            return [self.add(rec)]
        result = self.client.add(
            messages,
            user_id=owner,
            agent_id=agent_id or None,
            run_id=run_id or None,
            metadata=metadata,
        )
        out: list[MemoryRecord] = []
        items: list[Any]
        if isinstance(result, dict):
            items = list(result.get("results") or [])
        elif isinstance(result, list):
            items = result
        else:
            items = []
        if not items:
            # Pending async — store a stub for local tracking
            stub = MemoryRecord(
                content=str(messages)[:500],
                owner=owner,
                origin_agent=agent_id or owner,
                execution_id=run_id,
                metadata={**(metadata or {}), "status": "pending"},
                namespace="agents/",
                source="mem0",
            )
            return [stub]
        for item in items:
            if isinstance(item, dict):
                out.append(_parse_mem0_item(item, owner=owner, namespace="agents/"))
        return out

    def search(self, query: SearchQuery) -> list[SearchHit]:
        raw = self.client.search(
            query.text,
            user_id=query.owner,
            top_k=query.limit,
            threshold=self.cfg.search_threshold,
            rerank=self.cfg.rerank,
        )
        hits: list[SearchHit] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rec = _parse_mem0_item(item, owner=query.owner, namespace=query.namespace or "agents/")
            if query.namespace:
                qns = normalize_namespace(query.namespace)
                if rec.namespace != qns and not rec.namespace.startswith(qns):
                    # metadata filter post-pass
                    if rec.metadata.get("namespace") not in {qns, query.namespace}:
                        continue
            if query.memory_types and rec.type not in query.memory_types:
                continue
            if rec.importance < query.min_importance:
                continue
            score = float(item.get("score") or 0.0)
            hits.append(SearchHit(record=rec, score=score, signals={"mem0": score}))
        return hits[: query.limit]

    def get(self, memory_id: str) -> MemoryRecord | None:
        item = self.client.get(memory_id)
        if not item:
            return None
        return _parse_mem0_item(item, owner=str(item.get("user_id") or "default"), namespace="agents/")

    def delete(self, memory_id: str) -> bool:
        return self.client.delete(memory_id)

    def list_ids(self, *, owner: str = "", namespace: str = "") -> list[str]:
        # Mem0 OSS list via search broad query — best-effort
        if not owner:
            return []
        hits = self.search(SearchQuery(text="*", owner=owner, namespace=namespace or None, limit=100))
        return [h.record.uuid for h in hits]

    def health(self) -> dict[str, Any]:
        h = self.client.health()
        h["healthy"] = bool(h.get("available"))
        return h
