"""
TextCandidate — official GEPA candidate is ``dict[str, str]`` components.

Maps to official: candidate mapping component_name -> component text
(``gepa.core.adapter.Candidate``).

ArmCascade/AROP: text artifacts only (prompts, OKF policies, tool docs).
Forbidden: NUMA, threads, KleidiAI, kernels, hardware scheduling.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

# Components that may appear in GEPA candidates (text only).
ALLOWED_COMPONENT_PREFIXES = (
    "system_prompt",
    "planner_prompt",
    "reviewer_prompt",
    "routing_policy",
    "compression_policy",
    "context_template",
    "governor_policy",
    "reasoning_policy",
    "okf_",
    "tool_",
    "mcp_",
    "playbook_",
    "workflow_",
)

FORBIDDEN_KEYS = frozenset(
    {
        "thread_count",
        "numa_placement",
        "openmp_schedule",
        "cpu_affinity",
        "sve2",
        "kleidiai",
        "memory_allocator",
        "thread_pool",
        "inference_kernel",
        "hardware_scheduling",
        "draft_len",
        "accept_threshold",
        "verify_batch",
        "speculation_depth",
    }
)

PARETO_OBJECTIVES = (
    "accuracy",
    "latency",
    "cost",
    "reasoning_tokens",
    "tool_calls",
    "compression_ratio",
    "prompt_length",
    "context_length",
    "memory",
    "cpu",
    "acceptance_rate",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(components: Mapping[str, str]) -> str:
    blob = json.dumps(dict(sorted(components.items())), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def validate_text_components(components: Mapping[str, str]) -> dict[str, str]:
    """Reject hardware/knob keys; keep only string text components."""
    out: dict[str, str] = {}
    for key, value in components.items():
        if key in FORBIDDEN_KEYS:
            raise ValueError(f"GEPA forbids non-text optimization target: {key}")
        if not isinstance(value, str):
            raise TypeError(f"GEPA component values must be str, got {type(value)} for {key}")
        out[key] = value
    return out


@dataclass(frozen=True, slots=True)
class MutationEvent:
    at: datetime
    parent_id: str | None
    rationale: str
    components_updated: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MergeEvent:
    at: datetime
    parent_a: str
    parent_b: str
    rationale: str
    components_from_a: tuple[str, ...]
    components_from_b: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TextCandidate:
    """Immutable versioned text candidate — never overwrite; append to pool."""

    id: str
    version: str
    components: Mapping[str, str]
    created_at: datetime
    parent_ids: tuple[str, ...] = ()
    content_hash: str = ""
    scores: Mapping[str, float] = field(default_factory=dict)
    per_task_scores: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    mutation_history: tuple[MutationEvent, ...] = ()
    merge_history: tuple[MergeEvent, ...] = ()
    approved: bool = False
    deployed: bool = False

    @classmethod
    def create(
        cls,
        components: Mapping[str, str],
        *,
        version: str = "v0",
        parent_ids: tuple[str, ...] | list[str] = (),
        scores: Mapping[str, float] | None = None,
        per_task_scores: Mapping[str, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
        mutation_history: tuple[MutationEvent, ...] = (),
        merge_history: tuple[MergeEvent, ...] = (),
        candidate_id: str | None = None,
    ) -> TextCandidate:
        comps = validate_text_components(components)
        return cls(
            id=candidate_id or f"tc_{uuid.uuid4().hex[:10]}",
            version=version,
            components=comps,
            created_at=_utcnow(),
            parent_ids=tuple(parent_ids),
            content_hash=content_hash(comps),
            scores=dict(scores or {}),
            per_task_scores=dict(per_task_scores or {}),
            metadata=dict(metadata or {}),
            mutation_history=mutation_history,
            merge_history=merge_history,
        )

    def with_scores(
        self,
        scores: Mapping[str, float],
        *,
        per_task_scores: Mapping[str, float] | None = None,
    ) -> TextCandidate:
        return TextCandidate(
            id=self.id,
            version=self.version,
            components=dict(self.components),
            created_at=self.created_at,
            parent_ids=self.parent_ids,
            content_hash=self.content_hash,
            scores=dict(scores),
            per_task_scores=dict(per_task_scores or self.per_task_scores),
            metadata=dict(self.metadata),
            mutation_history=self.mutation_history,
            merge_history=self.merge_history,
            approved=self.approved,
            deployed=self.deployed,
        )

    def mark_approved(self) -> TextCandidate:
        return TextCandidate(
            id=self.id,
            version=self.version,
            components=dict(self.components),
            created_at=self.created_at,
            parent_ids=self.parent_ids,
            content_hash=self.content_hash,
            scores=dict(self.scores),
            per_task_scores=dict(self.per_task_scores),
            metadata=dict(self.metadata),
            mutation_history=self.mutation_history,
            merge_history=self.merge_history,
            approved=True,
            deployed=self.deployed,
        )

    def mark_deployed(self) -> TextCandidate:
        return TextCandidate(
            id=self.id,
            version=self.version,
            components=dict(self.components),
            created_at=self.created_at,
            parent_ids=self.parent_ids,
            content_hash=self.content_hash,
            scores=dict(self.scores),
            per_task_scores=dict(self.per_task_scores),
            metadata=dict(self.metadata),
            mutation_history=self.mutation_history,
            merge_history=self.merge_history,
            approved=self.approved,
            deployed=True,
        )

    def mean_score(self) -> float:
        if "aggregate" in self.scores:
            return float(self.scores["aggregate"])
        if self.per_task_scores:
            return sum(self.per_task_scores.values()) / len(self.per_task_scores)
        if self.scores:
            return sum(self.scores.values()) / len(self.scores)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "components": dict(self.components),
            "created_at": self.created_at.isoformat(),
            "parent_ids": list(self.parent_ids),
            "content_hash": self.content_hash,
            "scores": dict(self.scores),
            "per_task_scores": dict(self.per_task_scores),
            "metadata": dict(self.metadata),
            "approved": self.approved,
            "deployed": self.deployed,
        }
