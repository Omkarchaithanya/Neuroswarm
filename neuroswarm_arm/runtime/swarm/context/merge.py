"""Typed merge of SwarmContext domains with conflict policies."""

from __future__ import annotations

from typing import Any

from .budget import BudgetContext, BudgetUsage
from .context import SwarmContext
from .events import ContextUpdated, EventBus
from .exceptions import MergeConflictError
from .execution import ExecutionContext
from .knowledge import KnowledgeContext
from .memory import MemoryContext
from .models import ConflictPolicy
from .tools import ToolContext


def _union_list(a: list[Any], b: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for item in list(a) + list(b):
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_dict(
    parent: dict[str, Any],
    child: dict[str, Any],
    policy: ConflictPolicy,
    *,
    field: str,
) -> dict[str, Any]:
    if policy is ConflictPolicy.PREFER_PARENT:
        out = dict(child)
        out.update(parent)
        return out
    if policy is ConflictPolicy.PREFER_CHILD:
        out = dict(parent)
        out.update(child)
        return out
    if policy is ConflictPolicy.UNION:
        out = dict(parent)
        out.update(child)
        return out
    if policy is ConflictPolicy.RAISE:
        conflicts = set(parent) & set(child)
        real = [k for k in conflicts if parent[k] != child[k]]
        if real:
            raise MergeConflictError(f"dict conflict on {field}: {real}", field=field)
        out = dict(parent)
        out.update(child)
        return out
    # SUM_USAGE not meaningful for arbitrary dicts — prefer child
    out = dict(parent)
    out.update(child)
    return out


def merge_budget(
    parent: BudgetContext,
    child: BudgetContext,
    *,
    policy: ConflictPolicy = ConflictPolicy.SUM_USAGE,
) -> BudgetContext:
    if policy is ConflictPolicy.PREFER_PARENT:
        return parent.model_copy(deep=True)
    if policy is ConflictPolicy.PREFER_CHILD:
        return child.model_copy(deep=True)
    if policy is ConflictPolicy.RAISE:
        if parent.envelope_id and child.envelope_id and parent.envelope_id != child.envelope_id:
            raise MergeConflictError("budget envelope_id conflict", field="envelope_id")
    # Prefer non-null limits from parent (shared envelope), sum usage
    used = BudgetUsage(
        cost_usd=parent.used.cost_usd + child.used.cost_usd
        if policy is ConflictPolicy.SUM_USAGE
        else max(parent.used.cost_usd, child.used.cost_usd),
        tokens=parent.used.tokens + child.used.tokens
        if policy is ConflictPolicy.SUM_USAGE
        else max(parent.used.tokens, child.used.tokens),
        latency_ms=max(parent.used.latency_ms, child.used.latency_ms),
        energy_j=parent.used.energy_j + child.used.energy_j
        if policy is ConflictPolicy.SUM_USAGE
        else max(parent.used.energy_j, child.used.energy_j),
        memory_bytes=max(parent.used.memory_bytes, child.used.memory_bytes),
        cpu_cores_s=parent.used.cpu_cores_s + child.used.cpu_cores_s
        if policy is ConflictPolicy.SUM_USAGE
        else max(parent.used.cpu_cores_s, child.used.cpu_cores_s),
        reasoning_tokens=parent.used.reasoning_tokens + child.used.reasoning_tokens
        if policy is ConflictPolicy.SUM_USAGE
        else max(parent.used.reasoning_tokens, child.used.reasoning_tokens),
    )
    return BudgetContext(
        cost_usd_limit=parent.cost_usd_limit if parent.cost_usd_limit is not None else child.cost_usd_limit,
        tokens_limit=parent.tokens_limit if parent.tokens_limit is not None else child.tokens_limit,
        latency_ms_limit=parent.latency_ms_limit
        if parent.latency_ms_limit is not None
        else child.latency_ms_limit,
        energy_j_limit=parent.energy_j_limit if parent.energy_j_limit is not None else child.energy_j_limit,
        memory_bytes_limit=parent.memory_bytes_limit
        if parent.memory_bytes_limit is not None
        else child.memory_bytes_limit,
        cpu_cores_s_limit=parent.cpu_cores_s_limit
        if parent.cpu_cores_s_limit is not None
        else child.cpu_cores_s_limit,
        reasoning_tokens_limit=parent.reasoning_tokens_limit
        if parent.reasoning_tokens_limit is not None
        else child.reasoning_tokens_limit,
        used=used,
        cost_usd_used=used.cost_usd,
        tokens_used=used.tokens,
        latency_ms_used=used.latency_ms,
        energy_j_used=used.energy_j,
        memory_bytes_used=used.memory_bytes,
        reasoning_tokens_used=used.reasoning_tokens,
        envelope_id=parent.envelope_id or child.envelope_id,
        frozen=parent.frozen or child.frozen,
        energy_estimate_j=parent.energy_estimate_j or child.energy_estimate_j,
        metadata=_merge_dict(parent.metadata, child.metadata, ConflictPolicy.UNION, field="budget.metadata"),
    )


def merge_memory(
    parent: MemoryContext,
    child: MemoryContext,
    *,
    policy: ConflictPolicy = ConflictPolicy.UNION,
) -> MemoryContext:
    return MemoryContext(
        session_id=child.session_id or parent.session_id,
        checkpoint_id=child.checkpoint_id or parent.checkpoint_id,
        memory_pressure=max(parent.memory_pressure, child.memory_pressure),
        tier_hint=child.tier_hint or parent.tier_hint,
        keys=_union_list(parent.keys, child.keys),
        working_memory=_merge_dict(parent.working_memory, child.working_memory, policy, field="working"),
        short_term_memory=_merge_dict(
            parent.short_term_memory, child.short_term_memory, policy, field="short"
        ),
        scratchpad=_merge_dict(parent.scratchpad, child.scratchpad, policy, field="scratch"),
        temporary_variables=_merge_dict(
            parent.temporary_variables, child.temporary_variables, policy, field="temps"
        ),
        long_term_memory_ref=child.long_term_memory_ref
        if not child.long_term_memory_ref.is_empty()
        else parent.long_term_memory_ref,
        mem0_reference=child.mem0_reference if not child.mem0_reference.is_empty() else parent.mem0_reference,
        okf_reference=child.okf_reference if not child.okf_reference.is_empty() else parent.okf_reference,
        compression=child.compression if child.compression.strategy else parent.compression,
        metadata=_merge_dict(parent.metadata, child.metadata, ConflictPolicy.UNION, field="mem.meta"),
    )


def merge_knowledge(
    parent: KnowledgeContext,
    child: KnowledgeContext,
    *,
    policy: ConflictPolicy = ConflictPolicy.UNION,
) -> KnowledgeContext:
    _ = policy
    return KnowledgeContext(
        namespaces=_union_list(parent.namespaces, child.namespaces),
        documents=_union_list(parent.documents, child.documents),
        policies=_union_list(parent.policies, child.policies),
        prompts=_union_list(parent.prompts, child.prompts),
        workflows=_union_list(parent.workflows, child.workflows),
        embedding_model=child.embedding_model or parent.embedding_model,
        embedding_refs=_union_list(parent.embedding_refs, child.embedding_refs),
        retrieval=child.retrieval if child.retrieval.query else parent.retrieval,
        knowledge_reference=child.knowledge_reference
        if not child.knowledge_reference.is_empty()
        else parent.knowledge_reference,
        okf_reference=child.okf_reference if not child.okf_reference.is_empty() else parent.okf_reference,
        metadata=_merge_dict(parent.metadata, child.metadata, ConflictPolicy.UNION, field="know.meta"),
    )


def merge_tools(
    parent: ToolContext,
    child: ToolContext,
    *,
    policy: ConflictPolicy = ConflictPolicy.UNION,
) -> ToolContext:
    _ = policy
    return ToolContext(
        registry=child.registry if not child.registry.is_empty() else parent.registry,
        available_tools=_union_list(parent.available_tools, child.available_tools),
        selected_tools=_union_list(parent.selected_tools, child.selected_tools),
        capabilities=_union_list(parent.capabilities, child.capabilities),
        permissions=_union_list(parent.permissions, child.permissions),
        history=_union_list(parent.history, child.history),
        metadata=_merge_dict(parent.metadata, child.metadata, ConflictPolicy.UNION, field="tools.meta"),
    )


def merge_execution(
    parent: ExecutionContext,
    child: ExecutionContext,
    *,
    policy: ConflictPolicy = ConflictPolicy.UNION,
) -> ExecutionContext:
    retries = dict(parent.retries)
    for k, v in child.retries.items():
        retries[k] = max(retries.get(k, 0), v)
    return ExecutionContext(
        run_id=child.run_id or parent.run_id,
        numa_node=child.numa_node if child.numa_node is not None else parent.numa_node,
        pool_hint=child.pool_hint or parent.pool_hint,
        timeout_s=child.timeout_s if child.timeout_s is not None else parent.timeout_s,
        baggage=_merge_dict(parent.baggage, child.baggage, policy, field="baggage"),
        available_tools=_union_list(parent.available_tools, child.available_tools),
        available_models=_union_list(parent.available_models, child.available_models),
        confidence=child.confidence if child.confidence is not None else parent.confidence,
        current_node=child.current_node or parent.current_node,
        current_agent=child.current_agent or parent.current_agent,
        completed_nodes=_union_list(parent.completed_nodes, child.completed_nodes),
        pending_nodes=_union_list(
            [n for n in parent.pending_nodes if n not in child.completed_nodes],
            [n for n in child.pending_nodes if n not in parent.completed_nodes and n not in child.completed_nodes],
        ),
        failed_nodes=_union_list(parent.failed_nodes, child.failed_nodes),
        retries=retries,
        failures=_union_list(parent.failures, child.failures),
        checkpoint_ids=_union_list(parent.checkpoint_ids, child.checkpoint_ids),
        timeline=_union_list(parent.timeline, child.timeline),
        node_results=_merge_dict(parent.node_results, child.node_results, ConflictPolicy.PREFER_CHILD, field="results"),
        node_statuses=_merge_dict(
            parent.node_statuses, child.node_statuses, ConflictPolicy.PREFER_CHILD, field="statuses"
        ),
        depth=max(parent.depth, child.depth),
        metadata=_merge_dict(parent.metadata, child.metadata, ConflictPolicy.UNION, field="exec.meta"),
    )


def merge_metrics(parent: Any, child: Any) -> Any:
    return parent.model_copy(
        update={
            "snapshot_count": parent.snapshot_count + child.snapshot_count,
            "propagation_count": parent.propagation_count + child.propagation_count,
            "merge_count": parent.merge_count + child.merge_count + 1,
            "diff_count": parent.diff_count + child.diff_count,
            "checkpoint_count": parent.checkpoint_count + child.checkpoint_count,
            "execution_depth": max(parent.execution_depth, child.execution_depth),
            "context_size_bytes": max(parent.context_size_bytes, child.context_size_bytes),
            "memory_ref_count": max(parent.memory_ref_count, child.memory_ref_count),
            "knowledge_ref_count": max(parent.knowledge_ref_count, child.knowledge_ref_count),
            "budget_usage_ratio": max(parent.budget_usage_ratio, child.budget_usage_ratio),
            "custom": {**parent.custom, **child.custom},
        }
    )


def merge_contexts(
    parent: SwarmContext,
    child: SwarmContext,
    *,
    policy: ConflictPolicy = ConflictPolicy.UNION,
    budget_policy: ConflictPolicy = ConflictPolicy.SUM_USAGE,
    events: EventBus | None = None,
) -> SwarmContext:
    """Fan-in merge after parallel DAG branches."""
    merged = parent.evolve(
        budget=merge_budget(parent.budget, child.budget, policy=budget_policy),
        memory=merge_memory(parent.memory, child.memory, policy=policy),
        knowledge=merge_knowledge(parent.knowledge, child.knowledge, policy=policy),
        tools=merge_tools(parent.tools, child.tools, policy=policy),
        execution=merge_execution(parent.execution, child.execution, policy=policy),
        metrics=merge_metrics(parent.metrics, child.metrics),
        checkpoints=_union_list(parent.checkpoints, child.checkpoints),
        tags=_union_list(parent.tags, child.tags),
        labels={**parent.labels, **child.labels},
        metadata=_merge_dict(parent.metadata, child.metadata, policy, field="metadata"),
        extra=_merge_dict(parent.extra, child.extra, policy, field="extra"),
        current_node=child.current_node or parent.current_node,
        current_agent=child.current_agent or parent.current_agent,
        history=_union_list(list(parent.history), list(child.history)),
    )
    if events is not None:
        events.emit(
            ContextUpdated(
                merged.swarm_id,
                kind="merge",
                child_swarm_id=child.swarm_id,
                policy=policy.value,
            )
        )
    return merged.refresh_metrics()
