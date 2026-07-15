"""FinOps report generation."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .envelope import BudgetEnvelope
from .schemas import ChargebackTags, utcnow
from .tracker import BudgetRuntimeState


class BudgetReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    limits: dict[str, float]
    remaining: dict[str, float]
    consumed: dict[str, float]
    violations: list[dict[str, str]] = Field(default_factory=list)
    degrade_actions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class ExecutionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    accounting: dict[str, Any]
    phase: str
    aborted: bool = False
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class CostReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    estimated_cost_usd: float
    list_cost_usd: float
    effective_cost_usd: float
    planner_overhead_usd: float
    chargeback: ChargebackTags
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class EnergyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    energy_joules: float
    tokens_per_watt: float
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class PlannerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    degrade_actions: list[str]
    preferred_tier: int
    preferred_quantization: str
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class ResourceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    peak_memory_bytes: float
    kv_bytes: float
    cpu_seconds: float
    tool_calls: int
    retries: int
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class TelemetryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    estimate_errors: dict[str, float]
    tokens_per_usd: float
    tokens_per_watt: float
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class ReportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: BudgetReport
    execution: ExecutionReport
    cost: CostReport
    energy: EnergyReport
    planner: PlannerReport
    resource: ResourceReport
    telemetry: TelemetryReport

    def as_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget.model_dump(),
            "execution": self.execution.model_dump(),
            "cost": self.cost.model_dump(),
            "energy": self.energy.model_dump(),
            "planner": self.planner.model_dump(),
            "resource": self.resource.model_dump(),
            "telemetry": self.telemetry.model_dump(),
        }


class ReportBuilder:
    def build(
        self,
        envelope: BudgetEnvelope,
        state: BudgetRuntimeState,
        *,
        chargeback: ChargebackTags | None = None,
    ) -> ReportBundle:
        eid = str(envelope.envelope_id)
        acc = state.accounting
        remaining = state.remaining_map()
        consumed = {k: float(v.consumed) for k, v in state.categories.items()}
        limits = {k: float(v.limit) for k, v in state.categories.items()}
        violations = [
            {"dim": k, "violation": v.violation.value, "hardness": v.hardness.value}
            for k, v in state.categories.items()
            if v.violation.value != "none"
        ]
        tokens = max(1, acc.total_tokens)
        cost = max(acc.estimated_cost_usd, 1e-12)
        joules = max(acc.estimated_energy_joules, 1e-12)
        # watts approx from joules / cpu_seconds
        watts = joules / max(acc.cpu_seconds, 1e-6)
        tokens_per_usd = tokens / cost
        tokens_per_watt = tokens / max(watts, 1e-6)
        tags = chargeback or ChargebackTags(
            tenant_id=envelope.tenant_id,
            agent_id=envelope.agent_id,
            workflow=envelope.workflow,
            model_tier=envelope.preferences.preferred_model_tier,
            list_cost_usd=acc.estimated_cost_usd,
            effective_cost_usd=acc.estimated_cost_usd,
        )
        return ReportBundle(
            budget=BudgetReport(
                envelope_id=eid,
                limits=limits,
                remaining=remaining,
                consumed=consumed,
                violations=violations,
                degrade_actions=list(state.degrade_actions),
            ),
            execution=ExecutionReport(
                envelope_id=eid,
                accounting=acc.snapshot(),
                phase=state.phase.value,
                aborted=state.aborted,
            ),
            cost=CostReport(
                envelope_id=eid,
                estimated_cost_usd=acc.estimated_cost_usd,
                list_cost_usd=tags.list_cost_usd,
                effective_cost_usd=tags.effective_cost_usd,
                planner_overhead_usd=acc.planner_overhead_usd,
                chargeback=tags,
            ),
            energy=EnergyReport(
                envelope_id=eid,
                energy_joules=acc.estimated_energy_joules,
                tokens_per_watt=tokens_per_watt,
            ),
            planner=PlannerReport(
                envelope_id=eid,
                degrade_actions=list(state.degrade_actions),
                preferred_tier=envelope.preferences.preferred_model_tier,
                preferred_quantization=envelope.preferences.preferred_quantization,
            ),
            resource=ResourceReport(
                envelope_id=eid,
                peak_memory_bytes=acc.peak_memory_bytes,
                kv_bytes=acc.kv_cache_bytes,
                cpu_seconds=acc.cpu_seconds,
                tool_calls=acc.tool_calls,
                retries=acc.retries,
            ),
            telemetry=TelemetryReport(
                envelope_id=eid,
                estimate_errors=dict(state.estimate_errors),
                tokens_per_usd=tokens_per_usd,
                tokens_per_watt=tokens_per_watt,
            ),
        )
