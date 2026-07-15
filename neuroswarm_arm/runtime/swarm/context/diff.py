"""Structured diffs across SwarmContext domains."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .context import SwarmContext
from .models import _Base
from .snapshot import SwarmContextSnapshot, restore_snapshot


class FieldDiff(_Base):
    path: str
    before: Any = None
    after: Any = None


class ContextDiff(_Base):
    """Structured multi-domain context diff."""

    left_id: str = ""
    right_id: str = ""
    left_hash: str = ""
    right_hash: str = ""
    identical: bool = False
    execution: list[FieldDiff] = Field(default_factory=list)
    budget: list[FieldDiff] = Field(default_factory=list)
    memory: list[FieldDiff] = Field(default_factory=list)
    knowledge: list[FieldDiff] = Field(default_factory=list)
    tools: list[FieldDiff] = Field(default_factory=list)
    metadata: list[FieldDiff] = Field(default_factory=list)
    other: list[FieldDiff] = Field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.identical or not (
            self.execution
            or self.budget
            or self.memory
            or self.knowledge
            or self.tools
            or self.metadata
            or self.other
        )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


def _diff_mapping(before: dict[str, Any], after: dict[str, Any], prefix: str) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    keys = set(before) | set(after)
    for k in sorted(keys):
        b = before.get(k)
        a = after.get(k)
        if b != a:
            diffs.append(FieldDiff(path=f"{prefix}.{k}", before=b, after=a))
    return diffs


def _diff_scalar(path: str, before: Any, after: Any) -> list[FieldDiff]:
    if before == after:
        return []
    return [FieldDiff(path=path, before=before, after=after)]


def diff_budget(left: SwarmContext, right: SwarmContext) -> list[FieldDiff]:
    lb, rb = left.budget, right.budget
    diffs: list[FieldDiff] = []
    for name in (
        "cost_usd_limit",
        "cost_usd_used",
        "tokens_limit",
        "tokens_used",
        "latency_ms_limit",
        "latency_ms_used",
        "energy_j_limit",
        "energy_j_used",
        "memory_bytes_limit",
        "memory_bytes_used",
        "reasoning_tokens_limit",
        "reasoning_tokens_used",
        "envelope_id",
        "frozen",
    ):
        diffs.extend(_diff_scalar(f"budget.{name}", getattr(lb, name), getattr(rb, name)))
    diffs.extend(_diff_mapping(lb.metadata, rb.metadata, "budget.metadata"))
    return diffs


def diff_memory(left: SwarmContext, right: SwarmContext) -> list[FieldDiff]:
    lm, rm = left.memory, right.memory
    diffs: list[FieldDiff] = []
    for name in ("session_id", "checkpoint_id", "memory_pressure", "tier_hint"):
        diffs.extend(_diff_scalar(f"memory.{name}", getattr(lm, name), getattr(rm, name)))
    if lm.keys != rm.keys:
        diffs.append(FieldDiff(path="memory.keys", before=lm.keys, after=rm.keys))
    diffs.extend(_diff_mapping(lm.working_memory, rm.working_memory, "memory.working"))
    diffs.extend(_diff_mapping(lm.scratchpad, rm.scratchpad, "memory.scratchpad"))
    diffs.extend(_diff_mapping(lm.metadata, rm.metadata, "memory.metadata"))
    return diffs


def diff_execution(left: SwarmContext, right: SwarmContext) -> list[FieldDiff]:
    le, re = left.execution, right.execution
    diffs: list[FieldDiff] = []
    for name in (
        "run_id",
        "current_node",
        "current_agent",
        "confidence",
        "depth",
        "timeout_s",
    ):
        diffs.extend(_diff_scalar(f"execution.{name}", getattr(le, name), getattr(re, name)))
    for name in ("completed_nodes", "pending_nodes", "failed_nodes"):
        if getattr(le, name) != getattr(re, name):
            diffs.append(
                FieldDiff(path=f"execution.{name}", before=getattr(le, name), after=getattr(re, name))
            )
    diffs.extend(_diff_mapping(le.node_statuses, re.node_statuses, "execution.node_statuses"))
    diffs.extend(_diff_mapping(le.node_results, re.node_results, "execution.node_results"))
    return diffs


def diff_metadata(left: SwarmContext, right: SwarmContext) -> list[FieldDiff]:
    diffs = _diff_mapping(left.metadata, right.metadata, "metadata")
    diffs.extend(_diff_mapping(left.labels, right.labels, "labels"))
    if left.tags != right.tags:
        diffs.append(FieldDiff(path="tags", before=left.tags, after=right.tags))
    return diffs


def diff_contexts(left: SwarmContext, right: SwarmContext) -> ContextDiff:
    lh = left.content_hash()
    rh = right.content_hash()
    if lh == rh:
        return ContextDiff(
            left_id=left.swarm_id,
            right_id=right.swarm_id,
            left_hash=lh,
            right_hash=rh,
            identical=True,
        )
    know = []
    if left.knowledge.namespaces != right.knowledge.namespaces:
        know.append(
            FieldDiff(
                path="knowledge.namespaces",
                before=left.knowledge.namespaces,
                after=right.knowledge.namespaces,
            )
        )
    tools = []
    if left.tools.available_tools != right.tools.available_tools:
        tools.append(
            FieldDiff(
                path="tools.available_tools",
                before=left.tools.available_tools,
                after=right.tools.available_tools,
            )
        )
    other: list[FieldDiff] = []
    for name in ("request_id", "workflow_id", "execution_id", "session_id", "version"):
        other.extend(_diff_scalar(name, getattr(left, name), getattr(right, name)))
    return ContextDiff(
        left_id=left.swarm_id,
        right_id=right.swarm_id,
        left_hash=lh,
        right_hash=rh,
        identical=False,
        execution=diff_execution(left, right),
        budget=diff_budget(left, right),
        memory=diff_memory(left, right),
        knowledge=know,
        tools=tools,
        metadata=diff_metadata(left, right),
        other=other,
    )


def diff_snapshots(a: SwarmContextSnapshot, b: SwarmContextSnapshot) -> ContextDiff:
    return diff_contexts(restore_snapshot(a), restore_snapshot(b))
