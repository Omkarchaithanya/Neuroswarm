"""Execution accounting ledger for a single request."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .schemas import utcnow


class ExecutionAccounting(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    uncached_in_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cpu_seconds: float = 0.0
    wall_clock_ms: float = 0.0
    queue_wait_ms: float = 0.0
    execution_time_ms: float = 0.0
    streaming_time_ms: float = 0.0
    memory_bytes: float = 0.0
    peak_memory_bytes: float = 0.0
    average_memory_bytes: float = 0.0
    _memory_samples: int = 0
    kv_cache_bytes: float = 0.0
    tool_calls: int = 0
    retries: int = 0
    backend_calls: int = 0
    estimated_cost_usd: float = 0.0
    estimated_energy_joules: float = 0.0
    planner_overhead_usd: float = 0.0
    updated_at: Any = Field(default_factory=utcnow)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        return int(self.prompt_tokens + self.completion_tokens + self.reasoning_tokens)

    def record_tokens(
        self,
        *,
        prompt: int = 0,
        completion: int = 0,
        reasoning: int = 0,
        uncached_in: int = 0,
        cache_write: int = 0,
        cache_read: int = 0,
    ) -> None:
        self.prompt_tokens += max(0, int(prompt))
        self.completion_tokens += max(0, int(completion))
        self.reasoning_tokens += max(0, int(reasoning))
        self.uncached_in_tokens += max(0, int(uncached_in))
        self.cache_write_tokens += max(0, int(cache_write))
        self.cache_read_tokens += max(0, int(cache_read))
        self.updated_at = utcnow()

    def record_memory(self, bytes_used: float) -> None:
        b = max(0.0, float(bytes_used))
        self.memory_bytes = b
        self.peak_memory_bytes = max(self.peak_memory_bytes, b)
        n = self._memory_samples + 1
        self.average_memory_bytes = (
            (self.average_memory_bytes * self._memory_samples) + b
        ) / n
        self._memory_samples = n
        self.updated_at = utcnow()

    def record_timing(
        self,
        *,
        wall_ms: float = 0.0,
        queue_ms: float = 0.0,
        exec_ms: float = 0.0,
        stream_ms: float = 0.0,
        cpu_s: float = 0.0,
    ) -> None:
        self.wall_clock_ms += max(0.0, wall_ms)
        self.queue_wait_ms += max(0.0, queue_ms)
        self.execution_time_ms += max(0.0, exec_ms)
        self.streaming_time_ms += max(0.0, stream_ms)
        self.cpu_seconds += max(0.0, cpu_s)
        self.updated_at = utcnow()

    def record_kv(self, bytes_used: float) -> None:
        self.kv_cache_bytes = max(self.kv_cache_bytes, max(0.0, float(bytes_used)))
        self.updated_at = utcnow()

    def record_tool(self, n: int = 1) -> None:
        self.tool_calls += max(0, int(n))
        self.updated_at = utcnow()

    def record_retry(self, n: int = 1) -> None:
        self.retries += max(0, int(n))
        self.updated_at = utcnow()

    def record_backend(self, n: int = 1) -> None:
        self.backend_calls += max(0, int(n))
        self.updated_at = utcnow()

    def record_cost(self, usd: float) -> None:
        self.estimated_cost_usd += max(0.0, float(usd))
        self.updated_at = utcnow()

    def record_energy(self, joules: float) -> None:
        self.estimated_energy_joules += max(0.0, float(joules))
        self.updated_at = utcnow()

    def record_planner(self, usd: float) -> None:
        self.planner_overhead_usd += max(0.0, float(usd))
        self.updated_at = utcnow()

    def as_dimension_delta(self) -> dict[str, float]:
        return {
            "prompt_tokens": float(self.prompt_tokens),
            "completion_tokens": float(self.completion_tokens),
            "reasoning_tokens": float(self.reasoning_tokens),
            "tokens_total": float(self.total_tokens),
            "cost_usd": float(self.estimated_cost_usd + self.planner_overhead_usd),
            "energy_joules": float(self.estimated_energy_joules),
            "memory_bytes": float(self.peak_memory_bytes),
            "kv_bytes": float(self.kv_cache_bytes),
            "tool_calls": float(self.tool_calls),
            "retries": float(self.retries),
            "cpu_seconds": float(self.cpu_seconds),
            "latency_ms": float(self.wall_clock_ms),
            "streaming_ms": float(self.streaming_time_ms),
        }

    def snapshot(self) -> dict[str, Any]:
        data = self.model_dump()
        data["total_tokens"] = self.total_tokens
        data.pop("_memory_samples", None)
        return data
