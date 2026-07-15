"""Raw observation events feeding the AWPP feature pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Mapping


@dataclass(slots=True)
class Observation:
    """Single execution / telemetry observation."""

    ts: float = field(default_factory=time)
    agent_id: str = ""
    session_id: str = ""
    workflow_id: str = ""
    task_id: str = ""
    event_type: str = ""
    node_from: str = ""
    node_to: str = ""
    model: str = ""
    quant: str = ""
    tool: str = ""
    backend: str = ""
    cascade_tier: int = 0
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    kv_pages_used: int = 0
    cache_hit: bool = False
    cache_miss: bool = False
    memory_hits: int = 0
    cpu_util: float = 0.0
    ram_pressure: float = 0.0
    kv_pressure: float = 0.0
    cold_start: bool = False
    prompt_hash: str = ""
    resource: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "event_type": self.event_type,
            "node_from": self.node_from,
            "node_to": self.node_to,
            "model": self.model,
            "quant": self.quant,
            "tool": self.tool,
            "backend": self.backend,
            "cascade_tier": self.cascade_tier,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "kv_pages_used": self.kv_pages_used,
            "cache_hit": self.cache_hit,
            "cache_miss": self.cache_miss,
            "memory_hits": self.memory_hits,
            "cpu_util": self.cpu_util,
            "ram_pressure": self.ram_pressure,
            "kv_pressure": self.kv_pressure,
            "cold_start": self.cold_start,
            "prompt_hash": self.prompt_hash,
            "resource": dict(self.resource),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Observation:
        return cls(
            ts=float(data.get("ts") or time()),
            agent_id=str(data.get("agent_id") or ""),
            session_id=str(data.get("session_id") or ""),
            workflow_id=str(data.get("workflow_id") or ""),
            task_id=str(data.get("task_id") or ""),
            event_type=str(data.get("event_type") or ""),
            node_from=str(data.get("node_from") or ""),
            node_to=str(data.get("node_to") or ""),
            model=str(data.get("model") or ""),
            quant=str(data.get("quant") or ""),
            tool=str(data.get("tool") or ""),
            backend=str(data.get("backend") or ""),
            cascade_tier=int(data.get("cascade_tier") or 0),
            latency_ms=float(data.get("latency_ms") or 0.0),
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            kv_pages_used=int(data.get("kv_pages_used") or 0),
            cache_hit=bool(data.get("cache_hit") or False),
            cache_miss=bool(data.get("cache_miss") or False),
            memory_hits=int(data.get("memory_hits") or 0),
            cpu_util=float(data.get("cpu_util") or 0.0),
            ram_pressure=float(data.get("ram_pressure") or 0.0),
            kv_pressure=float(data.get("kv_pressure") or 0.0),
            cold_start=bool(data.get("cold_start") or False),
            prompt_hash=str(data.get("prompt_hash") or ""),
            resource={str(k): float(v) for k, v in dict(data.get("resource") or {}).items()},
            metadata=dict(data.get("metadata") or {}),
        )
