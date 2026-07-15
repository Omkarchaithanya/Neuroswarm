"""Task cost estimation for cost-aware scheduling."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces import IKVPressureProvider
from ..interfaces.types import PoolKind, PriorityClass, ResourceEstimate


class TaskCostEstimator:
    """Combine static task hints with live KV / memory pressure."""

    def __init__(
        self,
        kv: IKVPressureProvider | None = None,
        memory_pressure_fn: object | None = None,
    ) -> None:
        self._kv = kv
        self._memory_pressure_fn = memory_pressure_fn

    def estimate(
        self,
        *,
        pool: PoolKind = PoolKind.BACKGROUND,
        priority: PriorityClass = PriorityClass.NORMAL,
        task_weight: float = 1.0,
        agent_weight: float = 1.0,
        expected_latency_ms: float = 50.0,
        model_warmness: float = 0.5,
        queue_length: int = 0,
        extras: Mapping[str, Any] | None = None,
    ) -> ResourceEstimate:
        kv_pressure = 0.0
        if self._kv is not None:
            snap = self._kv.pressure_snapshot()
            kv_pressure = float(snap.get("pressure", 0.0) or 0.0)

        mem_pressure = 0.0
        if callable(self._memory_pressure_fn):
            try:
                mem_pressure = float(self._memory_pressure_fn())  # type: ignore[misc]
            except Exception:
                mem_pressure = 0.0

        cpu_cost = {
            PoolKind.INFERENCE: 4.0,
            PoolKind.EMBEDDING: 2.5,
            PoolKind.TOOL: 1.5,
            PoolKind.MEMORY: 1.2,
            PoolKind.PLANNER: 1.0,
            PoolKind.BACKGROUND: 0.8,
            PoolKind.TELEMETRY: 0.3,
            PoolKind.MAINTENANCE: 0.5,
        }.get(pool, 1.0)

        if priority is PriorityClass.CRITICAL:
            cpu_cost *= 1.25

        confidence = 1.0 - min(0.5, kv_pressure * 0.3 + mem_pressure * 0.2)

        est = ResourceEstimate(
            cpu_cost=cpu_cost,
            memory_bytes=int((extras or {}).get("memory_bytes", 0)),
            kv_pressure=kv_pressure,
            expected_latency_ms=expected_latency_ms,
            queue_length=queue_length,
            task_weight=task_weight,
            agent_weight=agent_weight,
            model_warmness=model_warmness,
            scheduling_confidence=confidence,
        )
        return est
