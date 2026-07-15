"""Budget validator — hard/soft admit decisions."""

from __future__ import annotations

from typing import Mapping

from .categories import BudgetCategory
from .envelope import BudgetEnvelope
from .schemas import AdmitDecision, DimensionDelta, Hardness, ViolationState
from .tracker import BudgetRuntimeState


class BudgetValidator:
    def validate_envelope(
        self,
        envelope: BudgetEnvelope,
        *,
        projected: Mapping[str, float] | DimensionDelta | None = None,
    ) -> AdmitDecision:
        proj = self._as_map(projected)
        soft: list[str] = []
        hard: list[str] = []
        for name, cat in envelope.categories.items():
            need = float(proj.get(name, cat.projected or cat.estimated or 0.0))
            if need <= float(cat.limit) + 1e-12:
                continue
            msg = f"{name}: projected={need} > limit={cat.limit}"
            if cat.hardness is Hardness.HARD:
                hard.append(msg)
            else:
                soft.append(msg)
        return AdmitDecision(
            accepted=len(hard) == 0,
            soft_warnings=soft,
            hard_failures=hard,
        )

    def validate_state(
        self,
        state: BudgetRuntimeState,
        *,
        projected: Mapping[str, float] | DimensionDelta | None = None,
    ) -> AdmitDecision:
        proj = self._as_map(projected)
        soft: list[str] = []
        hard: list[str] = []
        for name, cat in state.categories.items():
            need = float(proj.get(name, cat.projected or 0.0))
            if need <= float(cat.remaining) + 1e-12:
                cat.refresh_violation()
                continue
            msg = f"{name}: projected={need} > remaining={cat.remaining}"
            if cat.hardness is Hardness.HARD:
                hard.append(msg)
                cat.violation = ViolationState.BREACHED
            else:
                soft.append(msg)
                cat.violation = ViolationState.WARNING
        return AdmitDecision(
            accepted=len(hard) == 0,
            soft_warnings=soft,
            hard_failures=hard,
        )

    def validate_categories(
        self, categories: Mapping[str, BudgetCategory]
    ) -> AdmitDecision:
        soft: list[str] = []
        hard: list[str] = []
        for name, cat in categories.items():
            v = cat.refresh_violation()
            if v is ViolationState.NONE:
                continue
            msg = f"{name}: violation={v.value}"
            if cat.hardness is Hardness.HARD and v is ViolationState.BREACHED:
                hard.append(msg)
            else:
                soft.append(msg)
        return AdmitDecision(
            accepted=len(hard) == 0,
            soft_warnings=soft,
            hard_failures=hard,
        )

    @staticmethod
    def _as_map(
        projected: Mapping[str, float] | DimensionDelta | None,
    ) -> dict[str, float]:
        if projected is None:
            return {}
        if isinstance(projected, DimensionDelta):
            return dict(projected.values)
        return {str(k): float(v) for k, v in projected.items()}
