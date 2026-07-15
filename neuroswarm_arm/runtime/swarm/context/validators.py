"""Structural validation for SwarmContext."""

from __future__ import annotations

from typing import Any

from .budget import BudgetContext
from .context import SwarmContext
from .exceptions import BudgetError, InvalidReferenceError, ValidationError, VersionMismatchError
from .models import ExternalRef, RegistryHandle
from .versioning import CONTEXT_SCHEMA_VERSION, assert_compatible


class ValidationReport:
    """Collect validation issues without always raising."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def raise_if_errors(self) -> None:
        if self.errors:
            raise ValidationError("; ".join(self.errors))

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def _check_ref(ref: ExternalRef, name: str, report: ValidationReport, *, require: bool = False) -> None:
    if require and ref.is_empty():
        report.error(f"missing required reference: {name}")
    if ref.ref_id and not ref.ref_id.strip():
        report.error(f"invalid empty ref_id on {name}")


def _check_registry(handle: RegistryHandle, name: str, report: ValidationReport) -> None:
    if handle.registry_id and not handle.registry_id.strip():
        report.error(f"invalid empty registry_id on {name}")


def validate_budget(budget: BudgetContext, report: ValidationReport | None = None) -> ValidationReport:
    report = report or ValidationReport()
    limits = [
        ("cost_usd_limit", budget.cost_usd_limit, budget.cost_usd_used),
        ("tokens_limit", budget.tokens_limit, budget.tokens_used),
        ("latency_ms_limit", budget.latency_ms_limit, budget.latency_ms_used),
        ("energy_j_limit", budget.energy_j_limit, budget.energy_j_used),
        ("reasoning_tokens_limit", budget.reasoning_tokens_limit, budget.reasoning_tokens_used),
    ]
    for name, limit, used in limits:
        if limit is not None and limit < 0:
            report.error(f"invalid budget {name}: {limit}")
        if used < 0:
            report.error(f"invalid budget usage for {name}: {used}")
    if budget.memory_bytes_limit is not None and budget.memory_bytes_limit < 0:
        report.error("invalid memory_bytes_limit")
    if budget.frozen and not budget.envelope_id:
        report.warn("frozen budget without envelope_id")
    return report


def validate_context(
    ctx: SwarmContext,
    *,
    require_request: bool = True,
    require_execution: bool = True,
    strict_version: bool = True,
) -> ValidationReport:
    report = ValidationReport()

    if require_request and ctx.request.is_empty():
        report.error("missing request: prompt/conversation/files empty")
    if require_execution and not ctx.execution.run_id and not ctx.execution_id:
        report.error("missing execution: run_id and execution_id empty")

    validate_budget(ctx.budget, report)

    if strict_version:
        try:
            assert_compatible(ctx.version)
        except VersionMismatchError as exc:
            report.error(str(exc))
        if ctx.schema_version != ctx.version:
            report.warn(
                f"schema_version ({ctx.schema_version}) != version ({ctx.version})"
            )

    _check_ref(ctx.mem0_reference, "mem0_reference", report)
    _check_ref(ctx.okf_reference, "okf_reference", report)
    _check_ref(ctx.knowledge_reference, "knowledge_reference", report)
    _check_ref(ctx.memory.mem0_reference, "memory.mem0_reference", report)
    _check_ref(ctx.memory.okf_reference, "memory.okf_reference", report)
    _check_registry(ctx.tool_registry, "tool_registry", report)
    _check_registry(ctx.agent_registry, "agent_registry", report)

    if ctx.metadata is not None and not isinstance(ctx.metadata, dict):
        report.error("invalid metadata: must be dict")

    # pressure already validated by pydantic; double-check range
    if not (0.0 <= ctx.memory.memory_pressure <= 1.0):
        report.error("invalid memory_pressure")

    return report


def assert_valid(ctx: SwarmContext, **kwargs: Any) -> SwarmContext:
    report = validate_context(ctx, **kwargs)
    report.raise_if_errors()
    return ctx


def assert_budget(budget: BudgetContext) -> BudgetContext:
    report = validate_budget(budget)
    if report.errors:
        raise BudgetError("; ".join(report.errors), field="budget")
    return budget


def assert_ref(ref: ExternalRef, *, name: str = "reference") -> ExternalRef:
    if ref.is_empty():
        raise InvalidReferenceError(f"empty reference: {name}", field=name)
    return ref
