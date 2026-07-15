"""Weighted deterministic swarm template selector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ._utils import clamp, stable_hash
from .events import SelectionPerformed, SwarmSelected
from .exceptions import SelectionError
from .lifecycle import is_selectable
from .models import (
    ScoreBreakdown,
    ScoredTemplate,
    ScoringWeights,
    SwarmSelectionRequest,
    SwarmSelectionResult,
)
from .template import SwarmTemplate

if TYPE_CHECKING:
    from .events import EventBus
    from .metrics import SwarmMetrics


def score_template(
    template: SwarmTemplate,
    request: SwarmSelectionRequest,
    *,
    weights: ScoringWeights,
) -> tuple[float, ScoreBreakdown, list[str]]:
    reasons: list[str] = []
    w = weights

    # Capability coverage
    needed_caps = set(request.required_capabilities)
    have_caps = set(template.capabilities.capability_keys()) | set(
        template.constraints.required_capabilities
    )
    if needed_caps:
        cap_score = len(needed_caps & have_caps) / len(needed_caps)
    else:
        cap_score = 1.0
    reasons.append(f"capability={cap_score:.2f}")

    # Budget fit (1.0 if within limits / no limits)
    budget_score = 1.0
    b = request.budget
    if b.max_cost_usd is not None and template.estimated_cost > b.max_cost_usd:
        budget_score = 0.0
    elif b.max_cost_usd and template.estimated_cost > 0:
        budget_score = clamp(1.0 - (template.estimated_cost / b.max_cost_usd) * 0.5, 0.0, 1.0)
    if b.max_latency_ms is not None and template.estimated_latency > b.max_latency_ms:
        budget_score = min(budget_score, 0.0)
    if b.max_memory_bytes is not None and template.estimated_memory > b.max_memory_bytes:
        budget_score = min(budget_score, 0.0)
    if b.max_tokens is not None and template.estimated_tokens > b.max_tokens:
        budget_score = min(budget_score, 0.0)
    reasons.append(f"budget_fit={budget_score:.2f}")

    # Latency preference (lower better)
    if template.estimated_latency <= 0:
        latency_score = 0.8
    elif b.max_latency_ms and b.max_latency_ms > 0:
        latency_score = clamp(1.0 - template.estimated_latency / b.max_latency_ms, 0.0, 1.0)
    else:
        latency_score = clamp(1.0 - template.estimated_latency / 60_000.0, 0.0, 1.0)
    reasons.append(f"latency={latency_score:.2f}")

    # Cost preference (lower better)
    if template.estimated_cost <= 0:
        cost_score = 0.8
    elif b.max_cost_usd and b.max_cost_usd > 0:
        cost_score = clamp(1.0 - template.estimated_cost / b.max_cost_usd, 0.0, 1.0)
    else:
        cost_score = clamp(1.0 - template.estimated_cost / 1.0, 0.0, 1.0)
    reasons.append(f"cost={cost_score:.2f}")

    # Agent / tool / model coverage
    checks = 0
    hits = 0
    for req_list, have_list in (
        (request.required_tools, template.required_tools),
        (request.required_models, template.required_models),
        (request.required_backends, template.required_backends),
        (request.required_context or request.context_keys, template.required_context),
    ):
        if req_list:
            checks += 1
            if set(req_list).issubset(set(have_list)):
                hits += 1
    agent_score = (hits / checks) if checks else 1.0
    if request.preferred_templates and template.id in request.preferred_templates:
        agent_score = clamp(agent_score + 0.1, 0.0, 1.0)
        reasons.append("preferred_boost")
    reasons.append(f"agent_coverage={agent_score:.2f}")

    priority_score = clamp(template.priority / 100.0, 0.0, 1.0)
    reasons.append(f"priority={priority_score:.2f}")

    breakdown = ScoreBreakdown(
        capability=cap_score,
        budget_fit=budget_score,
        latency=latency_score,
        cost=cost_score,
        agent_coverage=agent_score,
        priority=priority_score,
    )
    total = (
        w.capability * cap_score
        + w.budget_fit * budget_score
        + w.latency * latency_score
        + w.cost * cost_score
        + w.agent_coverage * agent_score
        + w.priority * priority_score
    )
    return total, breakdown, reasons


class SwarmSelector:
    """Select best matching swarm templates via hard filters + weighted scores."""

    def __init__(
        self,
        *,
        weights: ScoringWeights | None = None,
        events: EventBus | None = None,
        metrics: SwarmMetrics | None = None,
    ) -> None:
        self.weights = (weights or ScoringWeights()).normalized()
        self.events = events
        self.metrics = metrics

    def select(
        self,
        templates: Iterable[SwarmTemplate],
        request: SwarmSelectionRequest,
    ) -> SwarmSelectionResult:
        req_hash = stable_hash(request.model_dump(mode="json"))
        candidates = list(templates)
        rejected: list[dict] = []
        eligible: list[SwarmTemplate] = []

        for tpl in candidates:
            ok, reason = self._hard_filter(tpl, request)
            if not ok:
                rejected.append(
                    {"template_id": tpl.id, "name": tpl.name, "reason": reason}
                )
                continue
            eligible.append(tpl)

        scored: list[ScoredTemplate] = []
        for tpl in eligible:
            total, breakdown, reasons = score_template(
                tpl, request, weights=self.weights
            )
            scored.append(
                ScoredTemplate(
                    template_id=tpl.id,
                    name=tpl.name,
                    score=total,
                    breakdown=breakdown,
                    reasons=reasons,
                )
            )

        scored.sort(key=lambda s: (-s.score, s.name, s.template_id))
        limited = scored[: request.limit]
        result = SwarmSelectionResult(
            request_hash=req_hash,
            templates=limited,
            rejected=rejected,
            metadata={"eligible": len(eligible), "total": len(candidates)},
        )

        if self.metrics is not None:
            for s in limited:
                self.metrics.record_selection(
                    template_id=s.template_id,
                    workflow_type=request.workflow_type,
                )
        if self.events is not None:
            self.events.emit(
                SelectionPerformed(
                    request_hash=req_hash,
                    selected=[s.template_id for s in limited],
                    rejected_count=len(rejected),
                )
            )
            for s in limited:
                self.events.emit(
                    SwarmSelected(s.template_id, score=s.score, request_hash=req_hash)
                )

        return result

    def select_best(
        self,
        templates: Iterable[SwarmTemplate],
        request: SwarmSelectionRequest,
        *,
        require: bool = False,
    ) -> ScoredTemplate | None:
        result = self.select(templates, request)
        if not result.templates:
            if require:
                raise SelectionError("no eligible swarm template")
            return None
        return result.templates[0]

    def _hard_filter(
        self, template: SwarmTemplate, request: SwarmSelectionRequest
    ) -> tuple[bool, str]:
        if not is_selectable(template.status):
            return False, f"status={template.status.value}"
        if request.workflow_type and template.workflow_type:
            if template.workflow_type != request.workflow_type:
                return False, "workflow_type_mismatch"
        if request.category and template.category != request.category:
            return False, "category_mismatch"
        if request.tags:
            if not set(request.tags).issubset(set(template.tags)):
                return False, "tags_mismatch"
        if request.required_capabilities:
            have = set(template.capabilities.capability_keys()) | set(
                template.constraints.required_capabilities
            )
            if not set(request.required_capabilities).issubset(have):
                # soft: allow if template lists them in supported tasks/workflows
                supported = set(template.capabilities.supported_tasks) | set(
                    template.capabilities.supported_workflows
                )
                if not set(request.required_capabilities).issubset(have | supported):
                    return False, "capabilities_mismatch"
        if request.required_tools:
            if not set(request.required_tools).issubset(set(template.required_tools)):
                return False, "tools_mismatch"
        if request.required_models:
            if not set(request.required_models).issubset(set(template.required_models)):
                return False, "models_mismatch"
        if request.required_backends:
            if not set(request.required_backends).issubset(
                set(template.required_backends)
            ):
                return False, "backends_mismatch"
        b = request.budget
        if b.max_cost_usd is not None and template.estimated_cost > b.max_cost_usd:
            return False, "cost_exceeded"
        if b.max_latency_ms is not None and template.estimated_latency > b.max_latency_ms:
            return False, "latency_exceeded"
        if b.max_memory_bytes is not None and template.estimated_memory > b.max_memory_bytes:
            return False, "memory_exceeded"
        if b.max_tokens is not None and template.estimated_tokens > b.max_tokens:
            return False, "tokens_exceeded"
        if b.max_cpu_cores is not None and template.estimated_cpu > b.max_cpu_cores:
            return False, "cpu_exceeded"
        return True, "ok"
