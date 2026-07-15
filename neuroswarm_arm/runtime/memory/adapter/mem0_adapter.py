"""Mem0Adapter — NEXUS façade over official ``mem0.Memory`` (OSS v3).

Every method maps to SDK add/search/get/delete. Typed remember_* = ADD with
metadata.memory_type + metadata.namespace. update() = ADD-only superseding fact.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from neuroswarm_arm.runtime.memory.adapter.sdk_client import Mem0SdkClient
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.exceptions import MemoryProviderError
from neuroswarm_arm.runtime.memory.namespace import namespace_for_type, normalize_namespace
from neuroswarm_arm.runtime.memory.schemas import (
    MemoryRecord,
    MemoryType,
    PredictionResult,
    SearchHit,
    SearchQuery,
)


def _parse_item(item: dict[str, Any], *, owner: str, namespace: str = "agents/") -> MemoryRecord:
    mem_id = str(item.get("id") or item.get("memory_id") or uuid4())
    content = str(item.get("memory") or item.get("text") or item.get("data") or "")
    meta = dict(item.get("metadata") or {})
    try:
        mem_type = MemoryType(str(meta.get("memory_type", MemoryType.FACT.value)))
    except ValueError:
        mem_type = MemoryType.FACT
    created = item.get("created_at") or item.get("updated_at")
    ts = datetime.now(timezone.utc)
    if isinstance(created, str):
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            pass
    ns = meta.get("namespace", namespace)
    try:
        ns = normalize_namespace(str(ns))
    except Exception:  # noqa: BLE001
        ns = "agents/"
    return MemoryRecord(
        uuid=mem_id,
        content=content,
        type=mem_type,
        namespace=ns,
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


class Mem0Adapter:
    """Official-SDK adapter. Call sites must never import ``mem0`` directly."""

    name = "mem0_adapter"

    def __init__(
        self,
        cfg: MemoryRuntimeConfig | None = None,
        *,
        client: Mem0SdkClient | None = None,
        emergency: Any | None = None,
    ) -> None:
        self.cfg = cfg or MemoryRuntimeConfig()
        self.client = client or Mem0SdkClient(self.cfg)
        self.emergency = emergency  # JsonEmergencyFallback implementing IMemoryProvider
        self._use_emergency = not self.client.available

    @property
    def available(self) -> bool:
        return self.client.available or self.emergency is not None

    def _meta(
        self,
        memory_type: MemoryType | str,
        *,
        namespace: str | None = None,
        extra: dict[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        mt = memory_type if isinstance(memory_type, MemoryType) else MemoryType(str(memory_type))
        ns = namespace or namespace_for_type(mt)
        try:
            ns = normalize_namespace(ns)
        except Exception:  # noqa: BLE001
            ns = "agents/"
        meta: dict[str, Any] = {
            "memory_type": mt.value,
            "namespace": ns,
            "importance": float(fields.get("importance", 0.5)),
            "confidence": float(fields.get("confidence", 0.8)),
            "tags": list(fields.get("tags") or []),
            "origin_agent": str(fields.get("origin_agent") or ""),
            "workflow_id": str(fields.get("workflow_id") or ""),
            "execution_id": str(fields.get("execution_id") or ""),
            "cost": float(fields.get("cost", 0.0) or 0.0),
            "latency": float(fields.get("latency", 0.0) or 0.0),
            "success_score": float(fields.get("success_score", 0.0) or 0.0),
            "failure_reason": str(fields.get("failure_reason") or ""),
            "summary": str(fields.get("summary") or ""),
        }
        if extra:
            meta.update(extra)
        if fields.get("metadata"):
            meta.update(dict(fields["metadata"]))
        return meta

    def remember(
        self,
        messages: str | list[dict[str, str]],
        *,
        owner: str = "default",
        agent_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        """Official extraction path: ``Memory.add(messages, user_id=...)``."""
        if self._use_emergency and self.emergency is not None:
            return self.emergency.add_messages(
                messages, owner=owner, agent_id=agent_id, run_id=run_id, metadata=metadata
            )
        result = self.client.add(
            messages,
            user_id=owner,
            agent_id=agent_id or None,
            run_id=run_id or None,
            metadata=metadata,
        )
        items: list[Any]
        if isinstance(result, dict):
            items = list(result.get("results") or [])
        elif isinstance(result, list):
            items = result
        else:
            items = []
        if not items:
            return [
                MemoryRecord(
                    content=str(messages)[:500],
                    owner=owner,
                    origin_agent=agent_id or owner,
                    execution_id=run_id,
                    metadata={**(metadata or {}), "status": "pending"},
                    source="mem0",
                )
            ]
        return [_parse_item(i, owner=owner) for i in items if isinstance(i, dict)]

    def _remember_typed(
        self,
        content: str,
        memory_type: MemoryType,
        *,
        owner: str = "default",
        namespace: str | None = None,
        extra: dict[str, Any] | None = None,
        **kw: Any,
    ) -> MemoryRecord:
        meta = self._meta(memory_type, namespace=namespace, extra=extra, **kw)
        rec = MemoryRecord(
            content=content,
            type=memory_type,
            namespace=str(meta["namespace"]),
            owner=owner,
            importance=float(meta.get("importance", 0.5)),
            confidence=float(meta.get("confidence", 0.8)),
            metadata=meta,
            tags=list(meta.get("tags") or []),
            origin_agent=str(meta.get("origin_agent") or ""),
            workflow_id=str(meta.get("workflow_id") or ""),
            execution_id=str(meta.get("execution_id") or ""),
            cost=float(meta.get("cost", 0.0)),
            latency=float(meta.get("latency", 0.0)),
            success_score=float(meta.get("success_score", 0.0)),
            failure_reason=str(meta.get("failure_reason") or ""),
            summary=str(meta.get("summary") or ""),
            source="mem0",
        )
        if self._use_emergency and self.emergency is not None:
            return self.emergency.add(rec)
        result = self.client.add(
            content,
            user_id=owner,
            agent_id=rec.origin_agent or None,
            run_id=rec.execution_id or None,
            metadata=meta,
        )
        if isinstance(result, dict):
            results = result.get("results") or result.get("memories") or []
            if results and isinstance(results[0], dict):
                pid = results[0].get("id") or results[0].get("memory_id")
                if pid:
                    rec.provider_id = str(pid)
                    rec.uuid = str(pid)
        return rec

    def remember_fact(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(content, MemoryType.FACT, owner=owner, **kw)

    def remember_tool(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(content, MemoryType.TOOL, owner=owner, namespace="tools/", **kw)

    def remember_workflow(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(content, MemoryType.WORKFLOW, owner=owner, namespace="workflows/", **kw)

    def remember_reasoning(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(content, MemoryType.REASONING, owner=owner, namespace="reasoning/", **kw)

    def remember_cost(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(content, MemoryType.COST, owner=owner, namespace="cost/", **kw)

    def remember_performance(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(
            content, MemoryType.PERFORMANCE, owner=owner, namespace="performance/", **kw
        )

    def remember_reflection(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self._remember_typed(
            content, MemoryType.REFLECTION, owner=owner, namespace="reflection/", **kw
        )

    def search(
        self,
        query: str | SearchQuery,
        *,
        owner: str = "default",
        limit: int = 5,
        namespace: str | None = None,
        agent_id: str | None = None,
        **kw: Any,
    ) -> list[SearchHit]:
        """Official hybrid retrieval — do not bypass with custom vector search."""
        if isinstance(query, SearchQuery):
            q = query
        else:
            q = SearchQuery(text=query, owner=owner, limit=limit, namespace=namespace, **kw)
        if self._use_emergency and self.emergency is not None:
            return self.emergency.search(q)
        raw = self.client.search(
            q.text,
            user_id=q.owner,
            agent_id=agent_id,
            top_k=q.limit,
            threshold=self.cfg.search_threshold,
            rerank=self.cfg.rerank,
        )
        hits: list[SearchHit] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rec = _parse_item(item, owner=q.owner, namespace=q.namespace or "agents/")
            if q.namespace:
                try:
                    qns = normalize_namespace(q.namespace)
                    if rec.namespace != qns and not str(rec.metadata.get("namespace", "")).startswith(
                        qns.rstrip("/")
                    ):
                        if rec.namespace.split("/")[0] != qns.split("/")[0]:
                            continue
                except Exception:  # noqa: BLE001
                    pass
            if q.memory_types and rec.type not in q.memory_types:
                continue
            score = float(item.get("score") or 0.0)
            hits.append(SearchHit(record=rec, score=score, signals={"mem0_hybrid": score}))
        return hits[: q.limit]

    def retrieve(self, query: str | SearchQuery, **kw: Any) -> list[MemoryRecord]:
        return [h.record for h in self.search(query, **kw)]

    def forget(self, memory_id: str) -> bool:
        return self.delete(memory_id)

    def update(
        self,
        memory_id: str,
        content: str,
        *,
        owner: str = "default",
        memory_type: MemoryType = MemoryType.FACT,
        **kw: Any,
    ) -> MemoryRecord:
        """v3 ADD-only: store corrected fact with supersedes_id (no in-place UPDATE)."""
        meta_extra = dict(kw.pop("metadata", None) or {})
        meta_extra["supersedes_id"] = memory_id
        return self._remember_typed(
            content,
            memory_type,
            owner=owner,
            extra=meta_extra,
            **kw,
        )

    def delete(self, memory_id: str) -> bool:
        if self._use_emergency and self.emergency is not None:
            return self.emergency.delete(memory_id)
        return self.client.delete(memory_id)

    def summarize(self, memory_id: str | None = None, *, text: str = "", max_chars: int = 240) -> str:
        if memory_id and not text:
            item = None if self._use_emergency else self.client.get(memory_id)
            if item:
                text = str(item.get("memory") or item.get("text") or "")
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 3].rstrip() + "..."

    def predict(self, owner: str, *, context: str = "") -> PredictionResult:
        hits = self.search(context or "predict", owner=owner, limit=50)
        tools: Counter[str] = Counter()
        workflows: Counter[str] = Counter()
        for h in hits:
            rec = h.record
            tid = rec.metadata.get("tool_id") or ""
            if tid:
                tools[str(tid)] += 1
            if "success tool=" in rec.content:
                part = rec.content.split("success tool=", 1)[-1].split()[0]
                tools[part] += 2
            if rec.workflow_id:
                workflows[rec.workflow_id] += 1
        return PredictionResult(
            next_tool=tools.most_common(1)[0][0] if tools else "",
            next_workflow=workflows.most_common(1)[0][0] if workflows else "chat",
            confidence=min(0.95, 0.3 + 0.05 * (len(tools) + len(workflows))),
            scores={"tools": float(sum(tools.values())), "workflows": float(sum(workflows.values()))},
        )

    def health(self) -> dict[str, Any]:
        if self.client.available:
            return self.client.health()
        if self.emergency is not None:
            h = self.emergency.health()
            h["mode"] = "emergency_json"
            return h
        raise MemoryProviderError("no mem0 and no emergency provider")
