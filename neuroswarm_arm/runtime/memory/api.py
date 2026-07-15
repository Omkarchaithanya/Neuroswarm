"""NeuroMemory — public façade used by all NeuroSwarm modules.

Prefer Mem0Adapter for official SDK ops. Never import mem0ai from call sites.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from neuroswarm_arm.runtime.memory.schemas import (
    MemoryRecord,
    MemoryType,
    PredictionResult,
    ReflectionResult,
    SearchHit,
    SearchQuery,
)
from neuroswarm_arm.runtime.memory.service import MemoryRuntime

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.memory.adapter import Mem0Adapter


class NeuroMemory:
    """Domain façade — delegates storage to MemoryRuntime / Mem0Adapter."""

    def __init__(self, runtime: MemoryRuntime, *, adapter: Mem0Adapter | None = None) -> None:
        self.runtime = runtime
        self.adapter = adapter

    def remember(
        self,
        messages: str | list[dict[str, str]],
        *,
        owner: str = "default",
        agent_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        """Official Mem0 extraction: add(messages). Prefer adapter."""
        if self.adapter is not None:
            return self.adapter.remember(
                messages, owner=owner, agent_id=agent_id, run_id=run_id, metadata=metadata
            )
        # Fallback: store as fact via runtime provider
        if isinstance(messages, str):
            text = messages
        else:
            text = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages)
        return [self.remember_fact(text, owner=owner, origin_agent=agent_id, execution_id=run_id)]

    def update(self, memory_id: str, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        if self.adapter is not None:
            return self.adapter.update(memory_id, content, owner=owner, **kw)
        return self.remember_fact(content, owner=owner, metadata={"supersedes_id": memory_id, **(kw.get("metadata") or {})})

    def delete(self, memory_id: str) -> bool:
        if self.adapter is not None:
            return self.adapter.delete(memory_id)
        return self.forget(memory_id)

    def predict(self, owner: str, *, context: str = "") -> PredictionResult:
        if self.adapter is not None:
            return self.adapter.predict(owner, context=context)
        return self.predict_next(owner, context=context)

    # --- ingest ---
    def remember_fact(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.FACT, owner=owner, **kw)

    def remember_tool(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.TOOL, owner=owner, namespace="tools/", **kw)

    def remember_reasoning(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.REASONING, owner=owner, namespace="reasoning/", **kw)

    def remember_workflow(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.WORKFLOW, owner=owner, namespace="workflows/", **kw)

    def remember_execution(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.EXECUTION, owner=owner, namespace="execution/", **kw)

    def remember_agent(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.AGENT, owner=owner, namespace="agents/", **kw)

    def remember_user(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.USER, owner=owner, namespace="users/", **kw)

    def remember_cost(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.COST, owner=owner, namespace="cost/", **kw)

    def remember_latency(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.LATENCY, owner=owner, namespace="latency/", **kw)

    def remember_performance(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(
            content, MemoryType.PERFORMANCE, owner=owner, namespace="performance/", **kw
        )

    def remember_failure(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.FAILURE, owner=owner, namespace="execution/", **kw)

    def remember_success(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.SUCCESS, owner=owner, namespace="execution/", **kw)

    def remember_reflection(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(
            content, MemoryType.REFLECTION, owner=owner, namespace="reflection/", **kw
        )

    def remember_experience(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.EXPERIENCE, owner=owner, **kw)

    def remember_prompt(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.PROMPT, owner=owner, namespace="prompts/", **kw)

    def remember_benchmark(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(
            content, MemoryType.BENCHMARK, owner=owner, namespace="benchmarks/", **kw
        )

    def remember_evolution(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(
            content, MemoryType.EVOLUTION, owner=owner, namespace="evolution/", **kw
        )

    def remember_swarm(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(content, MemoryType.SWARM, owner=owner, namespace="swarm/", **kw)

    def remember_planning(self, content: str, *, owner: str = "default", **kw: Any) -> MemoryRecord:
        return self.runtime.remember_typed(
            content, MemoryType.PLANNING, owner=owner, namespace="planner/", **kw
        )

    # --- retrieve / lifecycle / cognition ---
    def search(self, query: SearchQuery | str, *, owner: str = "default", **kw: Any) -> list[SearchHit]:
        return self.runtime.search(query, owner=owner, **kw)

    def recall(self, owner: str, query: str, *, limit: int = 5, namespace: str | None = None) -> list[str]:
        return self.runtime.recall(owner, query, limit=limit, namespace=namespace)

    def retrieve(self, query: SearchQuery) -> list[MemoryRecord]:
        return self.runtime.retrieve(query)

    def archive(self, memory_id: str) -> MemoryRecord:
        return self.runtime.archive(memory_id)

    def forget(self, memory_id: str) -> bool:
        return self.runtime.forget(memory_id)

    def compress(self, owner: str, *, keep: int = 100) -> list[MemoryRecord]:
        return self.runtime.compress(owner, keep=keep)

    def summarize(self, memory_id: str) -> str:
        return self.runtime.summarize(memory_id)

    def predict_next(self, owner: str, *, context: str = "") -> PredictionResult:
        return self.runtime.predict_next(owner, context=context)

    def reflect(self, **kwargs: Any) -> ReflectionResult:
        return self.runtime.reflect(**kwargs)

    def rank(self, hits: list[SearchHit]) -> list[SearchHit]:
        return self.runtime.rank(hits)

    def promote(self, memory_id: str) -> MemoryRecord:
        return self.runtime.promote(memory_id)

    def demote(self, memory_id: str) -> MemoryRecord:
        return self.runtime.demote(memory_id)

    def link(self, a_id: str, b_id: str, *, rel: str = "related") -> None:
        return self.runtime.link(a_id, b_id, rel=rel)

    def merge(self, a_id: str, b_id: str) -> MemoryRecord:
        return self.runtime.merge(a_id, b_id)

    def health(self):
        return self.runtime.health_check()

    # --- legacy Mem0Fallback-compatible surface ---
    def add(self, agent_id: str, fact: str, metadata: dict[str, str] | None = None) -> None:
        meta = {k: v for k, v in (metadata or {}).items()}
        event = meta.get("event", "")
        tool_id = meta.get("tool_id", "")
        if event == "success":
            self.remember_success(
                fact,
                owner=agent_id,
                metadata=meta,
                tags=["tool", "success"],
                success_score=1.0,
                latency=float(meta.get("latency_ms", 0) or 0),
            )
            if tool_id:
                self.remember_tool(
                    fact,
                    owner=agent_id,
                    metadata={**meta, "tool_id": tool_id},
                    tags=["tool", "success"],
                    success_score=1.0,
                )
            return
        if event == "failure":
            self.remember_failure(
                fact,
                owner=agent_id,
                metadata=meta,
                failure_reason=meta.get("reason") or fact,
                tags=["tool", "failure"],
            )
            return
        self.remember_fact(fact, owner=agent_id, metadata=meta)

    def search_texts(self, agent_id: str, query: str, limit: int = 5) -> list[str]:
        return self.recall(agent_id, query, limit=limit)
