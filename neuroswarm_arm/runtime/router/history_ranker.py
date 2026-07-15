"""NeuroMemory-backed historical ranking signals for tool routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.memory import NeuroMemory, build_memory_runtime

from .models import RouteContext, ToolRecord


class HistoryRanker:
    def __init__(self, memory: Any | None = None, *, root: Path | None = None) -> None:
        if isinstance(memory, NeuroMemory):
            self.memory = memory
        elif memory is not None and hasattr(memory, "neuro"):
            self.memory = memory.neuro
        elif memory is not None and hasattr(memory, "add") and hasattr(memory, "search"):
            # Legacy Mem0Fallback — wrap via its neuro if present else use add/search
            self.memory = getattr(memory, "neuro", None) or memory
        else:
            self.memory = build_memory_runtime(root or Path("work/memory"))

    def _owner(self, agent_id: str) -> str:
        return agent_id or "default"

    def record_success(
        self,
        agent_id: str,
        tool: ToolRecord | str,
        *,
        latency_ms: float = 0.0,
        combo: list[str] | None = None,
    ) -> None:
        tool_id = tool if isinstance(tool, str) else tool.id
        owner = self._owner(agent_id)
        fact = f"success tool={tool_id} latency_ms={latency_ms}"
        meta = {"event": "success", "tool_id": tool_id, "latency_ms": str(latency_ms)}
        if isinstance(self.memory, NeuroMemory):
            self.memory.remember_tool(
                fact,
                owner=owner,
                metadata=meta,
                tags=["tool", "success"],
                success_score=1.0,
                latency=latency_ms,
            )
            self.memory.remember_success(
                fact,
                owner=owner,
                metadata=meta,
                success_score=1.0,
                latency=latency_ms,
            )
        else:
            self.memory.add(owner, fact, metadata=meta)
        if combo:
            combo_fact = f"combo success={'|'.join(combo)}"
            combo_meta = {"event": "combo_success", "tools": "|".join(combo)}
            if isinstance(self.memory, NeuroMemory):
                self.memory.remember_tool(combo_fact, owner=owner, metadata=combo_meta, tags=["combo"])
            else:
                self.memory.add(owner, combo_fact, metadata=combo_meta)

    def record_failure(self, agent_id: str, tool: ToolRecord | str, *, reason: str = "") -> None:
        tool_id = tool if isinstance(tool, str) else tool.id
        owner = self._owner(agent_id)
        fact = f"failure tool={tool_id} reason={reason}"
        meta = {"event": "failure", "tool_id": tool_id, "reason": reason}
        if isinstance(self.memory, NeuroMemory):
            self.memory.remember_failure(
                fact,
                owner=owner,
                metadata=meta,
                failure_reason=reason,
                tags=["tool", "failure"],
            )
            self.memory.remember_tool(
                fact,
                owner=owner,
                metadata=meta,
                tags=["tool", "failure"],
                success_score=0.0,
            )
        else:
            self.memory.add(owner, fact, metadata=meta)

    def scores_for(self, agent_id: str, tools: list[ToolRecord], query: str = "") -> dict[str, float]:
        owner = self._owner(agent_id)
        if isinstance(self.memory, NeuroMemory):
            hits = self.memory.recall(owner, query or "tool", limit=50)
        else:
            hits = self.memory.search(owner, query or "tool", limit=50)
        text = "\n".join(hits).lower()
        out: dict[str, float] = {}
        for tool in tools:
            success = text.count(f"success tool={tool.id}".lower())
            failure = text.count(f"failure tool={tool.id}".lower())
            total = success + failure
            if total == 0:
                out[tool.id] = tool.success_rate * 0.5
            else:
                out[tool.id] = success / total
        return out

    def preference_boost(self, agent_id: str, context: RouteContext | None = None) -> list[str]:
        ctx = context or RouteContext()
        owner = self._owner(agent_id or ctx.agent_id)
        q = ctx.conversation_excerpt or "prefer"
        if isinstance(self.memory, NeuroMemory):
            return self.memory.recall(owner, q, limit=10)
        return self.memory.search(owner, q, limit=10)
