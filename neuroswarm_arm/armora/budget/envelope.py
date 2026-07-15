"""Immutable BudgetEnvelope — the ARMORA runtime resource contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .categories import BudgetCategory, build_category
from .config import BudgetRuntimeConfig
from .schemas import (
    BackendPreferences,
    CancellationPolicy,
    EnvelopeTemplate,
    ExecutionSLA,
    FailurePolicy,
    Hardness,
    HardwareConstraints,
    QualityRequirement,
    new_envelope_id,
    utcnow,
)


class BudgetEnvelope(BaseModel):
    """Immutable after freeze(); categories hold limits only at freeze time."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    envelope_id: UUID = Field(default_factory=new_envelope_id)
    request_id: str = ""
    tenant_id: str = ""
    agent_id: str = ""
    agent_role: str = "default"
    workflow: str = "chat"
    priority: int = 0
    deadline: datetime | None = None
    sla: ExecutionSLA = Field(default_factory=ExecutionSLA)
    failure_policy: FailurePolicy = FailurePolicy.DEGRADE
    cancellation_policy: CancellationPolicy = CancellationPolicy.DRAIN
    quality: QualityRequirement = Field(default_factory=QualityRequirement)
    preferences: BackendPreferences = Field(default_factory=BackendPreferences)
    hardware: HardwareConstraints = Field(default_factory=HardwareConstraints)
    metadata: dict[str, Any] = Field(default_factory=dict)
    categories: dict[str, BudgetCategory] = Field(default_factory=dict)
    max_context_length: int = 32_768
    max_batch_size: int = 8
    max_worker_time_ms: float = 120_000.0
    max_queue_time_ms: float = 5_000.0
    max_backend_cost_usd: float = 0.05
    max_planner_cost_usd: float = 0.005
    max_cache_allocation_bytes: int = 1 * 1024 * 1024 * 1024
    max_memory_pages: int = 65_536
    frozen: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    frozen_at: datetime | None = None

    _mutable_guard: bool = PrivateAttr(default=True)

    def category(self, name: str) -> BudgetCategory:
        if name not in self.categories:
            raise KeyError(f"unknown budget category: {name}")
        return self.categories[name]

    def remaining_map(self) -> dict[str, float]:
        return {k: float(v.limit) for k, v in self.categories.items()}

    def limit_map(self) -> dict[str, float]:
        return {k: float(v.limit) for k, v in self.categories.items()}

    def freeze(self) -> "BudgetEnvelope":
        if self.frozen:
            return self
        data = self.model_dump()
        data["frozen"] = True
        data["frozen_at"] = utcnow()
        cats: dict[str, BudgetCategory] = {}
        for name, cat in self.categories.items():
            snap = cat.model_dump()
            snap.pop("remaining", None)
            snap["consumed"] = 0.0
            snap["reserved"] = 0.0
            snap["estimated"] = 0.0
            snap["projected"] = 0.0
            cats[name] = BudgetCategory.model_validate(snap)
        data["categories"] = {k: v.model_dump(exclude={"remaining"}) for k, v in cats.items()}
        data.pop("remaining", None)
        frozen = BudgetEnvelope.model_validate(data)
        return frozen

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": str(self.envelope_id),
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "workflow": self.workflow,
            "priority": self.priority,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "frozen": self.frozen,
            "sla": self.sla.model_dump(),
            "failure_policy": self.failure_policy.value,
            "cancellation_policy": self.cancellation_policy.value,
            "quality": self.quality.model_dump(),
            "preferences": self.preferences.model_dump(),
            "hardware": self.hardware.model_dump(),
            "limits": self.limit_map(),
            "max_context_length": self.max_context_length,
            "max_batch_size": self.max_batch_size,
            "max_worker_time_ms": self.max_worker_time_ms,
            "max_queue_time_ms": self.max_queue_time_ms,
            "max_backend_cost_usd": self.max_backend_cost_usd,
            "max_planner_cost_usd": self.max_planner_cost_usd,
            "max_cache_allocation_bytes": self.max_cache_allocation_bytes,
            "max_memory_pages": self.max_memory_pages,
            "metadata": dict(self.metadata),
        }


def _hardness(cfg: BudgetRuntimeConfig, dim: str) -> Hardness:
    mapping = {
        "cost_usd": cfg.cost_hard,
        "latency_ms": cfg.latency_hard,
        "memory_bytes": cfg.memory_hard,
        "energy_joules": cfg.energy_hard,
        "prompt_tokens": cfg.token_hard,
        "completion_tokens": cfg.token_hard,
        "reasoning_tokens": cfg.token_hard,
        "tokens_total": cfg.token_hard,
        "kv_bytes": cfg.kv_hard,
        "tool_calls": cfg.tool_hard,
        "cpu_seconds": cfg.compute_hard,
        "streaming_ms": cfg.streaming_hard,
        "retries": cfg.retry_hard,
        "concurrency": cfg.retry_hard,
    }
    return Hardness.HARD if mapping.get(dim, True) else Hardness.SOFT


def build_envelope_from_template(
    template: EnvelopeTemplate,
    cfg: BudgetRuntimeConfig,
    *,
    request_id: str,
    tenant_id: str = "",
    agent_id: str = "",
    workflow: str = "chat",
    extra_categories: Mapping[str, BudgetCategory] | None = None,
) -> BudgetEnvelope:
    def pick(val: float | int | None, default: float | int) -> float:
        return float(default if val is None else val)

    cost = pick(template.cost_usd, cfg.default_cost_usd)
    latency = pick(template.latency_ms, cfg.default_latency_ms)
    memory = pick(template.memory_bytes, cfg.default_memory_bytes)
    energy = pick(template.energy_joules, cfg.default_energy_joules)
    prompt = pick(template.prompt_tokens, cfg.default_prompt_tokens)
    completion = pick(template.completion_tokens, cfg.default_completion_tokens)
    reasoning = pick(template.reasoning_tokens, cfg.default_reasoning_tokens)
    kv = pick(template.kv_bytes, cfg.default_kv_bytes)
    tools = pick(template.tool_calls, cfg.default_tool_calls)
    cpu = pick(template.cpu_seconds, cfg.default_cpu_seconds)
    streaming = pick(template.streaming_ms, cfg.default_streaming_ms)
    retries = pick(template.retries, cfg.default_retries)
    concurrency = pick(template.concurrency, cfg.default_concurrency)
    tokens_total = prompt + completion + reasoning

    categories: dict[str, BudgetCategory] = {
        "cost_usd": build_category("cost_usd", limit=cost, hardness=_hardness(cfg, "cost_usd")),
        "latency_ms": build_category(
            "latency_ms", limit=latency, hardness=_hardness(cfg, "latency_ms")
        ),
        "memory_bytes": build_category(
            "memory_bytes", limit=memory, hardness=_hardness(cfg, "memory_bytes")
        ),
        "energy_joules": build_category(
            "energy_joules", limit=energy, hardness=_hardness(cfg, "energy_joules")
        ),
        "prompt_tokens": build_category(
            "prompt_tokens", limit=prompt, hardness=_hardness(cfg, "prompt_tokens")
        ),
        "completion_tokens": build_category(
            "completion_tokens",
            limit=completion,
            hardness=_hardness(cfg, "completion_tokens"),
        ),
        "reasoning_tokens": build_category(
            "reasoning_tokens",
            limit=reasoning,
            hardness=_hardness(cfg, "reasoning_tokens"),
        ),
        "tokens_total": build_category(
            "tokens_total", limit=tokens_total, hardness=_hardness(cfg, "tokens_total")
        ),
        "kv_bytes": build_category("kv_bytes", limit=kv, hardness=_hardness(cfg, "kv_bytes")),
        "tool_calls": build_category(
            "tool_calls", limit=tools, hardness=_hardness(cfg, "tool_calls")
        ),
        "cpu_seconds": build_category(
            "cpu_seconds", limit=cpu, hardness=_hardness(cfg, "cpu_seconds")
        ),
        "streaming_ms": build_category(
            "streaming_ms", limit=streaming, hardness=_hardness(cfg, "streaming_ms")
        ),
        "retries": build_category(
            "retries", limit=retries, hardness=_hardness(cfg, "retries")
        ),
        "concurrency": build_category(
            "concurrency", limit=concurrency, hardness=_hardness(cfg, "concurrency")
        ),
    }
    if extra_categories:
        categories.update(dict(extra_categories))

    prefs = BackendPreferences(
        preferred_quantization=template.preferred_quantization or "",
        preferred_backend=template.preferred_backend or "",
        preferred_model_tier=int(
            template.preferred_model_tier
            if template.preferred_model_tier is not None
            else 1
        ),
    )
    quality = QualityRequirement(
        min_confidence=float(
            template.min_confidence
            if template.min_confidence is not None
            else cfg.default_min_confidence
        )
    )
    return BudgetEnvelope(
        request_id=request_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        agent_role=template.agent_role or "default",
        workflow=workflow,
        priority=int(
            template.priority if template.priority is not None else cfg.default_priority
        ),
        sla=ExecutionSLA(max_e2e_latency_ms=latency),
        failure_policy=template.failure_policy,
        cancellation_policy=template.cancellation_policy,
        quality=quality,
        preferences=prefs,
        categories=categories,
        max_context_length=int(
            template.max_context_length
            if template.max_context_length is not None
            else cfg.default_max_context_length
        ),
        max_batch_size=int(
            template.max_batch_size
            if template.max_batch_size is not None
            else cfg.default_max_batch_size
        ),
        max_worker_time_ms=cfg.default_max_worker_time_ms,
        max_queue_time_ms=cfg.default_max_queue_time_ms,
        max_backend_cost_usd=min(cost, cfg.default_max_backend_cost_usd),
        max_planner_cost_usd=cfg.default_max_planner_cost_usd,
        max_cache_allocation_bytes=cfg.default_max_cache_allocation_bytes,
        max_memory_pages=cfg.default_max_memory_pages,
        metadata=dict(template.metadata),
        frozen=False,
    )
