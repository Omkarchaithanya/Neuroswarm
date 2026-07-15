"""Bidirectional bridge to legacy ``task_graph.context`` dataclasses.

Lazy-imports task_graph to avoid circular package imports at module load.
Does not mutate task_graph APIs.
"""

from __future__ import annotations

from typing import Any

from ..budget import BudgetContext as RichBudget
from ..context import SwarmContext
from ..execution import ExecutionContext as RichExecution
from ..memory import MemoryContext as RichMemory
from ..tools import ToolContext
from ..tracing import TraceContext


def to_task_graph_context(ctx: SwarmContext) -> Any:
    """Convert Context OS SwarmContext → legacy dataclass SwarmContext."""
    from neuroswarm_arm.runtime.swarm.task_graph.context import (
        BudgetContext as LegacyBudget,
        ExecutionContext as LegacyExecution,
        MemoryContext as LegacyMemory,
        SwarmContext as LegacySwarm,
        TracingContext as LegacyTracing,
    )

    tracing = LegacyTracing(
        trace_id=ctx.trace_context.trace_id,
        span_id=ctx.trace_context.span_id,
        parent_span_id=ctx.trace_context.parent_span_id,
        workflow_id=ctx.workflow_id or ctx.trace_context.workflow_id,
        request_id=ctx.request_id or ctx.trace_context.request_id,
        correlation_id=ctx.trace_context.correlation_id,
        agent_id=ctx.current_agent or ctx.trace_context.agent_id,
        execution_id=ctx.execution_id or ctx.trace_context.execution_id,
        baggage=dict(ctx.trace_context.baggage),
    )
    budget = LegacyBudget(
        cost_usd_limit=ctx.budget.cost_usd_limit,
        cost_usd_used=ctx.budget.cost_usd_used,
        tokens_limit=ctx.budget.tokens_limit,
        tokens_used=ctx.budget.tokens_used,
        latency_ms_limit=ctx.budget.latency_ms_limit,
        latency_ms_used=ctx.budget.latency_ms_used,
        energy_j_limit=ctx.budget.energy_j_limit,
        energy_j_used=ctx.budget.energy_j_used,
        envelope_id=ctx.budget.envelope_id,
        frozen=ctx.budget.frozen,
        metadata=dict(ctx.budget.metadata),
    )
    memory = LegacyMemory(
        session_id=ctx.session_id or ctx.memory.session_id,
        checkpoint_id=ctx.memory.checkpoint_id,
        memory_pressure=ctx.memory.memory_pressure,
        tier_hint=ctx.memory.tier_hint,
        keys=list(ctx.memory.keys),
        metadata=dict(ctx.memory.metadata),
    )
    execution = LegacyExecution(
        run_id=ctx.execution.run_id or ctx.execution_id,
        numa_node=ctx.execution.numa_node,
        pool_hint=ctx.execution.pool_hint,
        timeout_s=ctx.execution.timeout_s,
        baggage=dict(ctx.execution.baggage),
        available_tools=set(ctx.tools.available_tools or ctx.execution.available_tools),
        available_models=set(ctx.execution.available_models),
        confidence=ctx.execution.confidence,
    )
    extra = dict(ctx.extra)
    extra.setdefault("node_results", dict(ctx.execution.node_results))
    extra.setdefault("node_statuses", dict(ctx.execution.node_statuses))
    return LegacySwarm(
        swarm_id=ctx.swarm_id,
        execution=execution,
        memory=memory,
        budget=budget,
        tracing=tracing,
        extra=extra,
    )


def from_task_graph_context(legacy: Any) -> SwarmContext:
    """Convert legacy dataclass SwarmContext → Context OS SwarmContext."""
    tracing = TraceContext(
        trace_id=legacy.tracing.trace_id,
        span_id=legacy.tracing.span_id,
        parent_span_id=legacy.tracing.parent_span_id,
        workflow_id=legacy.tracing.workflow_id,
        request_id=legacy.tracing.request_id,
        correlation_id=legacy.tracing.correlation_id,
        agent_id=legacy.tracing.agent_id,
        execution_id=legacy.tracing.execution_id,
        baggage=dict(legacy.tracing.baggage),
    )
    budget = RichBudget(
        cost_usd_limit=legacy.budget.cost_usd_limit,
        cost_usd_used=legacy.budget.cost_usd_used,
        tokens_limit=legacy.budget.tokens_limit,
        tokens_used=legacy.budget.tokens_used,
        latency_ms_limit=legacy.budget.latency_ms_limit,
        latency_ms_used=legacy.budget.latency_ms_used,
        energy_j_limit=legacy.budget.energy_j_limit,
        energy_j_used=legacy.budget.energy_j_used,
        envelope_id=legacy.budget.envelope_id,
        frozen=legacy.budget.frozen,
        metadata=dict(legacy.budget.metadata),
    )
    memory = RichMemory(
        session_id=legacy.memory.session_id,
        checkpoint_id=legacy.memory.checkpoint_id,
        memory_pressure=legacy.memory.memory_pressure,
        tier_hint=legacy.memory.tier_hint,
        keys=list(legacy.memory.keys),
        metadata=dict(legacy.memory.metadata),
    )
    execution = RichExecution(
        run_id=legacy.execution.run_id,
        numa_node=legacy.execution.numa_node,
        pool_hint=legacy.execution.pool_hint,
        timeout_s=legacy.execution.timeout_s,
        baggage=dict(legacy.execution.baggage),
        available_tools=sorted(legacy.execution.available_tools),
        available_models=sorted(legacy.execution.available_models),
        confidence=legacy.execution.confidence,
        node_results=dict(legacy.extra.get("node_results", {})),
        node_statuses=dict(legacy.extra.get("node_statuses", {})),
    )
    return SwarmContext(
        swarm_id=legacy.swarm_id,
        request_id=legacy.tracing.request_id,
        workflow_id=legacy.tracing.workflow_id,
        execution_id=legacy.tracing.execution_id,
        session_id=legacy.memory.session_id,
        budget=budget,
        memory=memory,
        execution=execution,
        trace_context=tracing,
        tools=ToolContext(available_tools=sorted(legacy.execution.available_tools)),
        extra=dict(legacy.extra),
        current_agent=legacy.tracing.agent_id or None,
    )
