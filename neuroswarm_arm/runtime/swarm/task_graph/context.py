"""Context objects propagated into every Task Graph node.

No runtime logic — structural carriers only for HAOE / ARMORA / DIPA integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class TracingContext:
    """Correlation / OTel baggage for a node or workflow."""

    trace_id: str = field(default_factory=lambda: uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid4().hex)
    parent_span_id: str | None = None
    workflow_id: str = field(default_factory=lambda: uuid4().hex)
    request_id: str = field(default_factory=lambda: uuid4().hex)
    correlation_id: str = field(default_factory=lambda: uuid4().hex)
    agent_id: str = ""
    execution_id: str = field(default_factory=lambda: uuid4().hex)
    baggage: dict[str, str] = field(default_factory=dict)

    def child(self, *, agent_id: str | None = None) -> TracingContext:
        return TracingContext(
            trace_id=self.trace_id,
            span_id=uuid4().hex,
            parent_span_id=self.span_id,
            workflow_id=self.workflow_id,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            agent_id=agent_id if agent_id is not None else self.agent_id,
            execution_id=uuid4().hex,
            baggage=dict(self.baggage),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "workflow_id": self.workflow_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "agent_id": self.agent_id,
            "execution_id": self.execution_id,
            "baggage": dict(self.baggage),
        }


@dataclass(slots=True)
class BudgetContext:
    """Budget envelope snapshot visible to conditions / planners."""

    cost_usd_limit: float | None = None
    cost_usd_used: float = 0.0
    tokens_limit: float | None = None
    tokens_used: float = 0.0
    latency_ms_limit: float | None = None
    latency_ms_used: float = 0.0
    energy_j_limit: float | None = None
    energy_j_used: float = 0.0
    envelope_id: str | None = None
    frozen: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def remaining_cost(self) -> float | None:
        if self.cost_usd_limit is None:
            return None
        return max(0.0, self.cost_usd_limit - self.cost_usd_used)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_usd_limit": self.cost_usd_limit,
            "cost_usd_used": self.cost_usd_used,
            "tokens_limit": self.tokens_limit,
            "tokens_used": self.tokens_used,
            "latency_ms_limit": self.latency_ms_limit,
            "latency_ms_used": self.latency_ms_used,
            "energy_j_limit": self.energy_j_limit,
            "energy_j_used": self.energy_j_used,
            "envelope_id": self.envelope_id,
            "frozen": self.frozen,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class MemoryContext:
    """Memory / KV hints for a node (no MAKS logic)."""

    session_id: str | None = None
    checkpoint_id: str | None = None
    memory_pressure: float = 0.0
    tier_hint: str = ""
    keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "checkpoint_id": self.checkpoint_id,
            "memory_pressure": self.memory_pressure,
            "tier_hint": self.tier_hint,
            "keys": list(self.keys),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ExecutionContext:
    """Per-run execution baggage (cancellation handled separately by executor)."""

    run_id: str = field(default_factory=lambda: uuid4().hex)
    numa_node: int | None = None
    pool_hint: str = ""
    timeout_s: float | None = None
    baggage: dict[str, Any] = field(default_factory=dict)
    available_tools: set[str] = field(default_factory=set)
    available_models: set[str] = field(default_factory=set)
    confidence: float | None = None

    def child(self) -> ExecutionContext:
        return ExecutionContext(
            run_id=uuid4().hex,
            numa_node=self.numa_node,
            pool_hint=self.pool_hint,
            timeout_s=self.timeout_s,
            baggage=dict(self.baggage),
            available_tools=set(self.available_tools),
            available_models=set(self.available_models),
            confidence=self.confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "numa_node": self.numa_node,
            "pool_hint": self.pool_hint,
            "timeout_s": self.timeout_s,
            "baggage": dict(self.baggage),
            "available_tools": sorted(self.available_tools),
            "available_models": sorted(self.available_models),
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class SwarmContext:
    """Top-level context bundle delivered to every node."""

    swarm_id: str = field(default_factory=lambda: uuid4().hex)
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    memory: MemoryContext = field(default_factory=MemoryContext)
    budget: BudgetContext = field(default_factory=BudgetContext)
    tracing: TracingContext = field(default_factory=TracingContext)
    extra: dict[str, Any] = field(default_factory=dict)

    def child(self, *, agent_id: str | None = None) -> SwarmContext:
        return SwarmContext(
            swarm_id=self.swarm_id,
            execution=self.execution.child(),
            memory=MemoryContext(
                session_id=self.memory.session_id,
                checkpoint_id=self.memory.checkpoint_id,
                memory_pressure=self.memory.memory_pressure,
                tier_hint=self.memory.tier_hint,
                keys=list(self.memory.keys),
                metadata=dict(self.memory.metadata),
            ),
            budget=BudgetContext(
                cost_usd_limit=self.budget.cost_usd_limit,
                cost_usd_used=self.budget.cost_usd_used,
                tokens_limit=self.budget.tokens_limit,
                tokens_used=self.budget.tokens_used,
                latency_ms_limit=self.budget.latency_ms_limit,
                latency_ms_used=self.budget.latency_ms_used,
                energy_j_limit=self.budget.energy_j_limit,
                energy_j_used=self.budget.energy_j_used,
                envelope_id=self.budget.envelope_id,
                frozen=self.budget.frozen,
                metadata=dict(self.budget.metadata),
            ),
            tracing=self.tracing.child(agent_id=agent_id),
            extra=dict(self.extra),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "execution": self.execution.to_dict(),
            "memory": self.memory.to_dict(),
            "budget": self.budget.to_dict(),
            "tracing": self.tracing.to_dict(),
            "extra": dict(self.extra),
        }

    def as_condition_map(self) -> dict[str, Any]:
        """Flat map for condition evaluation."""
        return {
            "swarm": self.to_dict(),
            "confidence": self.execution.confidence,
            "budget": self.budget.to_dict(),
            "latency_ms_used": self.budget.latency_ms_used,
            "memory_pressure": self.memory.memory_pressure,
            "available_tools": set(self.execution.available_tools),
            "available_models": set(self.execution.available_models),
            "node_results": self.extra.get("node_results", {}),
            "node_statuses": self.extra.get("node_statuses", {}),
            **self.extra,
        }
