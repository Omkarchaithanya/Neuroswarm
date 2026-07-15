"""Read-only repositories over RCIS history for planner feedback."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import RCISRuntimeConfig
from .schemas import (
    Objective,
    RankedChoice,
    RankedChoices,
    RuntimeCostReport,
    WorkloadKey,
    safe_div,
)


def _ewma(values: list[float], alpha: float) -> float:
    if not values:
        return 0.0
    acc = float(values[0])
    for v in values[1:]:
        acc = alpha * float(v) + (1.0 - alpha) * acc
    return acc


def _rank(
    groups: dict[str, list[RuntimeCostReport]],
    *,
    objective: Objective,
    alpha: float,
    min_samples: int,
    limit: int,
) -> RankedChoices:
    choices: list[RankedChoice] = []
    for key, reports in groups.items():
        # Include groups even with few samples; confidence reflects sample size.
        if not reports:
            continue
        costs = [r.estimated_dollars for r in reports]
        lats = [r.latency_ms for r in reports]
        energies = [r.energy_estimate_joules for r in reports]
        qualities = [r.quality_score for r in reports]
        mean_cost = safe_div(sum(costs), float(len(costs)))
        mean_lat = safe_div(sum(lats), float(len(lats)))
        mean_energy = safe_div(sum(energies), float(len(energies)))
        mean_quality = safe_div(sum(qualities), float(len(qualities)))
        ewma_cost = _ewma(costs, alpha)
        ewma_lat = _ewma(lats, alpha)
        ewma_energy = _ewma(energies, alpha)
        ewma_quality = _ewma(qualities, alpha)

        if objective == Objective.COST:
            score = -ewma_cost
        elif objective == Objective.LATENCY:
            score = -ewma_lat
        elif objective == Objective.ENERGY:
            score = -ewma_energy
        elif objective == Objective.QUALITY:
            score = ewma_quality
        else:
            # Pareto-ish scalar: prefer low cost+latency+energy, high quality
            score = ewma_quality - (ewma_cost * 1000.0) - (ewma_lat / 1000.0) - (ewma_energy / 100.0)

        confidence = min(0.99, 0.3 + 0.05 * len(reports))
        choices.append(
            RankedChoice(
                key=key,
                score=score,
                samples=len(reports),
                mean_cost=mean_cost,
                mean_latency_ms=mean_lat,
                mean_energy_joules=mean_energy,
                mean_quality=mean_quality,
                confidence=confidence,
            )
        )
    choices.sort(key=lambda c: c.score, reverse=True)
    return RankedChoices(objective=objective, choices=choices[:limit], window=sum(len(v) for v in groups.values()))


class HistoryBackedRepos:
    def __init__(self, persistence: Any, cfg: RCISRuntimeConfig) -> None:
        self.persistence = persistence
        self.cfg = cfg

    def _load(self, **filters: Any) -> list[RuntimeCostReport]:
        return list(
            self.persistence.query_reports(limit=self.cfg.history_window, **filters)
        )


class BackendCostRepo(HistoryBackedRepos):
    def rank_by_cost(self, *, limit: int = 50) -> RankedChoices:
        reports = self._load()
        groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
        for r in reports:
            if r.backend:
                groups[r.backend].append(r)
        return _rank(
            groups,
            objective=Objective.COST,
            alpha=self.cfg.ewma_alpha,
            min_samples=self.cfg.feedback_min_samples,
            limit=limit,
        )

    def rank_by_latency(self, *, limit: int = 50) -> RankedChoices:
        reports = self._load()
        groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
        for r in reports:
            if r.backend:
                groups[r.backend].append(r)
        return _rank(
            groups,
            objective=Objective.LATENCY,
            alpha=self.cfg.ewma_alpha,
            min_samples=self.cfg.feedback_min_samples,
            limit=limit,
        )


class QuantCostRepo(HistoryBackedRepos):
    def rank_by_latency(self, *, model: str = "", limit: int = 50) -> RankedChoices:
        reports = self._load()
        groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
        for r in reports:
            if model and r.model != model:
                continue
            if r.quantization:
                groups[r.quantization].append(r)
        return _rank(
            groups,
            objective=Objective.LATENCY,
            alpha=self.cfg.ewma_alpha,
            min_samples=self.cfg.feedback_min_samples,
            limit=limit,
        )

    def rank_by_cost(self, *, model: str = "", limit: int = 50) -> RankedChoices:
        reports = self._load()
        groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
        for r in reports:
            if model and r.model != model:
                continue
            if r.quantization:
                groups[r.quantization].append(r)
        return _rank(
            groups,
            objective=Objective.COST,
            alpha=self.cfg.ewma_alpha,
            min_samples=self.cfg.feedback_min_samples,
            limit=limit,
        )


class ModelTierRepo(HistoryBackedRepos):
    def rank(self, objective: Objective, *, limit: int = 50) -> RankedChoices:
        reports = self._load()
        groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
        for r in reports:
            if r.model_tier:
                groups[r.model_tier].append(r)
        return _rank(
            groups,
            objective=objective,
            alpha=self.cfg.ewma_alpha,
            min_samples=self.cfg.feedback_min_samples,
            limit=limit,
        )


class SpecStrategyRepo(HistoryBackedRepos):
    def rank(self, workload: WorkloadKey, *, limit: int = 50) -> RankedChoices:
        reports = self._load()
        groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
        for r in reports:
            if workload.backend and r.backend != workload.backend:
                continue
            if workload.model_tier and r.model_tier != workload.model_tier:
                continue
            # Strategy key from planner trace or acceptance band
            strategy = str(
                r.planner_decision_trace.get("spec_strategy")
                or r.extensions.get("spec_strategy")
                or (
                    "spec_on"
                    if (r.accepted_speculative_tokens + r.rejected_speculative_tokens) > 0
                    else "spec_off"
                )
            )
            groups[strategy].append(r)
        return _rank(
            groups,
            objective=Objective.COST,
            alpha=self.cfg.ewma_alpha,
            min_samples=max(1, self.cfg.feedback_min_samples // 2),
            limit=limit,
        )
