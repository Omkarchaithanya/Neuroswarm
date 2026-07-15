"""Budget tracker — mutable runtime state + estimate/reserve/reconcile ledger."""

from __future__ import annotations

import threading
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .accounting import ExecutionAccounting
from .categories import BudgetCategory, build_category
from .envelope import BudgetEnvelope
from .schemas import DimensionDelta, Hardness, LifecyclePhase, ViolationState, utcnow


class BudgetRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    envelope_id: str
    phase: LifecyclePhase = LifecyclePhase.CREATE
    categories: dict[str, BudgetCategory] = Field(default_factory=dict)
    accounting: ExecutionAccounting = Field(default_factory=ExecutionAccounting)
    estimate_errors: dict[str, float] = Field(default_factory=dict)
    degrade_actions: list[str] = Field(default_factory=list)
    aborted: bool = False
    reject_reason: str = ""
    updated_at: Any = Field(default_factory=utcnow)

    def remaining(self, name: str) -> float:
        cat = self.categories[name]
        return float(cat.remaining)

    def remaining_map(self) -> dict[str, float]:
        return {k: float(v.remaining) for k, v in self.categories.items()}

    def snapshot(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "phase": self.phase.value,
            "categories": {k: v.snapshot() for k, v in self.categories.items()},
            "accounting": self.accounting.snapshot(),
            "estimate_errors": dict(self.estimate_errors),
            "degrade_actions": list(self.degrade_actions),
            "aborted": self.aborted,
            "reject_reason": self.reject_reason,
        }


class BudgetTracker:
    """Thread-safe per-request ledger keyed by envelope_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, BudgetRuntimeState] = {}
        self._envelopes: dict[str, BudgetEnvelope] = {}

    def register(self, envelope: BudgetEnvelope) -> BudgetRuntimeState:
        if not envelope.frozen:
            raise RuntimeError("BudgetTracker requires a frozen BudgetEnvelope")
        eid = str(envelope.envelope_id)
        cats = {
            name: build_category(
                name,
                limit=float(cat.limit),
                hardness=cat.hardness,
                unit=cat.unit,
                confidence=cat.confidence,
                metadata=dict(cat.metadata),
            )
            for name, cat in envelope.categories.items()
        }
        state = BudgetRuntimeState(
            envelope_id=eid,
            phase=LifecyclePhase.EXECUTE,
            categories=cats,
        )
        with self._lock:
            self._envelopes[eid] = envelope
            self._states[eid] = state
        return state

    def get_state(self, envelope_id: str | UUID) -> BudgetRuntimeState:
        eid = str(envelope_id)
        with self._lock:
            if eid not in self._states:
                raise KeyError(f"unknown envelope_id: {eid}")
            return self._states[eid]

    def get_envelope(self, envelope_id: str | UUID) -> BudgetEnvelope:
        eid = str(envelope_id)
        with self._lock:
            if eid not in self._envelopes:
                raise KeyError(f"unknown envelope_id: {eid}")
            return self._envelopes[eid]

    def set_phase(self, envelope_id: str | UUID, phase: LifecyclePhase) -> None:
        with self._lock:
            state = self.get_state(envelope_id)
            state.phase = phase
            state.updated_at = utcnow()

    def estimate(self, envelope_id: str | UUID, projected: Mapping[str, float]) -> None:
        with self._lock:
            state = self.get_state(envelope_id)
            for name, value in projected.items():
                if name not in state.categories:
                    continue
                cat = state.categories[name]
                cat.estimated = float(value)
                cat.projected = float(value)
                cat.refresh_violation()
            state.updated_at = utcnow()

    def reserve(self, envelope_id: str | UUID, amounts: Mapping[str, float]) -> bool:
        with self._lock:
            state = self.get_state(envelope_id)
            if state.aborted:
                return False
            # Validate all hard dims first
            for name, amount in amounts.items():
                if name not in state.categories:
                    continue
                cat = state.categories[name]
                if cat.hardness is Hardness.HARD and float(amount) > cat.remaining + 1e-12:
                    return False
            for name, amount in amounts.items():
                if name not in state.categories:
                    continue
                state.categories[name].apply_reserve(float(amount))
            state.phase = LifecyclePhase.CONSUME
            state.updated_at = utcnow()
            return True

    def reconcile(
        self,
        envelope_id: str | UUID,
        actual: Mapping[str, float],
        *,
        reserved: Mapping[str, float] | None = None,
    ) -> BudgetRuntimeState:
        with self._lock:
            state = self.get_state(envelope_id)
            reserved_map = dict(reserved or actual)
            for name, act in actual.items():
                if name not in state.categories:
                    continue
                cat = state.categories[name]
                res = float(reserved_map.get(name, 0.0))
                if res:
                    cat.release_reserve(res)
                cat.apply_consume(float(act))
                state.estimate_errors[name] = float(act) - float(cat.estimated or res)
            # Mirror into accounting for common dims
            acc = state.accounting
            if "prompt_tokens" in actual:
                acc.record_tokens(prompt=int(actual["prompt_tokens"]))
            if "completion_tokens" in actual:
                acc.record_tokens(completion=int(actual["completion_tokens"]))
            if "reasoning_tokens" in actual:
                acc.record_tokens(reasoning=int(actual["reasoning_tokens"]))
            if "cost_usd" in actual:
                acc.record_cost(float(actual["cost_usd"]))
            if "energy_joules" in actual:
                acc.record_energy(float(actual["energy_joules"]))
            if "memory_bytes" in actual:
                acc.record_memory(float(actual["memory_bytes"]))
            if "kv_bytes" in actual:
                acc.record_kv(float(actual["kv_bytes"]))
            if "tool_calls" in actual:
                acc.record_tool(int(actual["tool_calls"]))
            if "retries" in actual:
                acc.record_retry(int(actual["retries"]))
            if "cpu_seconds" in actual:
                acc.record_timing(cpu_s=float(actual["cpu_seconds"]))
            if "latency_ms" in actual:
                acc.record_timing(wall_ms=float(actual["latency_ms"]))
            if "streaming_ms" in actual:
                acc.record_timing(stream_ms=float(actual["streaming_ms"]))
            state.phase = LifecyclePhase.CHECK
            state.updated_at = utcnow()
            return state

    def consume(self, envelope_id: str | UUID, amounts: Mapping[str, float]) -> bool:
        """Direct consume without prior reserve (small ops)."""
        if not self.reserve(envelope_id, amounts):
            return False
        self.reconcile(envelope_id, amounts, reserved=amounts)
        return True

    def check_violations(self, envelope_id: str | UUID) -> list[dict[str, str]]:
        with self._lock:
            state = self.get_state(envelope_id)
            out: list[dict[str, str]] = []
            for name, cat in state.categories.items():
                v = cat.refresh_violation()
                if v is not ViolationState.NONE:
                    out.append(
                        {
                            "dim": name,
                            "violation": v.value,
                            "hardness": cat.hardness.value,
                        }
                    )
            return out

    def hard_breached(self, envelope_id: str | UUID) -> bool:
        return any(
            v["hardness"] == Hardness.HARD.value and v["violation"] == ViolationState.BREACHED.value
            for v in self.check_violations(envelope_id)
        )

    def abort(self, envelope_id: str | UUID, reason: str) -> None:
        with self._lock:
            state = self.get_state(envelope_id)
            state.aborted = True
            state.reject_reason = reason
            state.phase = LifecyclePhase.ABORTED
            state.updated_at = utcnow()

    def record_degrade(self, envelope_id: str | UUID, action: str) -> None:
        with self._lock:
            state = self.get_state(envelope_id)
            state.degrade_actions.append(action)
            state.updated_at = utcnow()

    def apply_limit_adjustment(
        self, envelope_id: str | UUID, adjustments: Mapping[str, float]
    ) -> None:
        """Runtime degrade may lower *effective* remaining by reducing limits on state only."""
        with self._lock:
            state = self.get_state(envelope_id)
            for name, new_limit in adjustments.items():
                if name not in state.categories:
                    continue
                cat = state.categories[name]
                cat.limit = max(float(cat.consumed + cat.reserved), float(new_limit))
                cat.refresh_violation()
            state.updated_at = utcnow()

    def cost_remaining(self, envelope_id: str | UUID) -> float:
        return self.get_state(envelope_id).remaining("cost_usd")

    def list_active(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())
