"""Memory Runtime adapter — wraps NeuroMemory; does not re-implement storage."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.acr.ir.bundles import MemoryBundle, MemoryItem
from neuroswarm_arm.runtime.acr.ir.plan import RetrievalExecutionPlan, RetrievalSource


def _estimate_tokens(text: str) -> int:
    return max(1, len((text or "").split()))


class MemoryRuntimeAdapter:
    """Thin adapter over NeuroMemory / Cognitive Memory Runtime."""

    def __init__(self, memory: Any | None = None) -> None:
        self._memory = memory

    def retrieve(self, plan: RetrievalExecutionPlan, owner: str = "default") -> MemoryBundle:
        bundle = MemoryBundle(request_id=plan.request_id)
        if self._memory is None:
            return bundle
        neuro = self._resolve()
        if neuro is None:
            return bundle

        mem_sources = {
            RetrievalSource.MEMORY,
            RetrievalSource.REFLECTION,
            RetrievalSource.REASONING,
            RetrievalSource.WORKFLOW,
            RetrievalSource.EXAMPLES,
        }
        for step in plan.ordered_steps():
            if step.source not in mem_sources:
                continue
            if step.lazy and step.priority < 0.5:
                continue
            try:
                texts = self._recall(neuro, owner, step.query, step)
            except Exception:
                texts = []
            for t in texts:
                content = t if isinstance(t, str) else str(getattr(t, "content", t))
                item = MemoryItem(
                    content=content,
                    namespace=(step.namespaces[0] if step.namespaces else ""),
                    memory_type=step.source.value,
                    score=step.priority,
                    importance=step.priority,
                    tokens=_estimate_tokens(content),
                    metadata={"step_id": step.id},
                )
                bundle.items.append(item)
            bundle.source_step_ids.append(step.id)
            # Soft token budget per step
            used = sum(i.tokens for i in bundle.items)
            if used >= plan.token_budget:
                break
        return bundle

    def _resolve(self) -> Any | None:
        m = self._memory
        if m is None:
            return None
        if hasattr(m, "recall") and hasattr(m, "search"):
            return m
        return getattr(m, "neuro", None) or getattr(m, "_memory", None)

    def _recall(self, neuro: Any, owner: str, query: str, step: Any) -> list[str]:
        ns = step.namespaces[0] if step.namespaces else None
        kwargs: dict[str, Any] = {"limit": step.limit}
        if ns:
            kwargs["namespace"] = ns
        if hasattr(neuro, "recall"):
            return list(neuro.recall(owner, query or "context", **kwargs) or [])
        if hasattr(neuro, "search_texts"):
            return list(neuro.search_texts(owner, query or "context", limit=step.limit) or [])
        return []
