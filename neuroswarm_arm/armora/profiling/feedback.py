"""Planner / RL feedback APIs — read-only; no RL implementation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import RPFRuntimeConfig
from .exporters import ProfileStore
from .schemas import RankedChoice, RankedChoices, RuntimeProfile


class ProfilerFeedbackService:
    """IProfilerFeedback — ranks from historical RuntimeProfile store."""

    def __init__(self, store: ProfileStore, cfg: RPFRuntimeConfig) -> None:
        self.store = store
        self.cfg = cfg

    def _profiles(self) -> list[RuntimeProfile]:
        return self.store.query(limit=self.cfg.history_window)

    async def hottest_backends(self, *, limit: int = 10) -> RankedChoices:
        return self.hottest_backends_sync(limit=limit)

    def hottest_backends_sync(self, *, limit: int = 10) -> RankedChoices:
        profiles = self._profiles()
        agg: dict[str, list[float]] = defaultdict(list)
        for p in profiles:
            key = p.backend.backend or "unknown"
            # "hot" = high CPU usage + execution time
            score = float(p.cpu.usage_percent) + float(p.execution.execution_time_ms) / 10.0
            agg[key].append(score)
        choices = self._rank(agg, limit=limit, higher_is_worse=True)
        return RankedChoices(choices=choices, objective="hottest_backend")

    async def worst_ipc_workloads(self, *, limit: int = 10) -> RankedChoices:
        return self.worst_ipc_workloads_sync(limit=limit)

    def worst_ipc_workloads_sync(self, *, limit: int = 10) -> RankedChoices:
        profiles = self._profiles()
        agg: dict[str, list[float]] = defaultdict(list)
        for p in profiles:
            key = p.backend.backend or p.workflow_id or "unknown"
            ipc = float(p.hardware.ipc or p.hardware.derived_ipc)
            if ipc <= 0:
                continue
            agg[key].append(ipc)
        choices = self._rank(agg, limit=limit, higher_is_worse=False)
        return RankedChoices(choices=choices, objective="worst_ipc")

    async def latency_percentiles(self, *, backend: str = "") -> RankedChoices:
        return self.latency_percentiles_sync(backend=backend)

    def latency_percentiles_sync(self, *, backend: str = "") -> RankedChoices:
        profiles = self._profiles()
        values: list[float] = []
        for p in profiles:
            if backend and p.backend.backend != backend:
                continue
            values.append(float(p.execution.execution_time_ms or p.cpu.wall_time_ms))
        if len(values) < self.cfg.feedback_min_samples:
            return RankedChoices(choices=[], objective="latency_percentiles")
        values.sort()
        n = len(values)

        def pct(p: float) -> float:
            idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
            return values[idx]

        choices = [
            RankedChoice(key="p50", score=pct(50), samples=n),
            RankedChoice(key="p90", score=pct(90), samples=n),
            RankedChoice(key="p99", score=pct(99), samples=n),
        ]
        return RankedChoices(choices=choices, objective="latency_percentiles")

    @staticmethod
    def _rank(
        agg: dict[str, list[float]],
        *,
        limit: int,
        higher_is_worse: bool,
    ) -> list[RankedChoice]:
        scored: list[RankedChoice] = []
        for key, vals in agg.items():
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            scored.append(RankedChoice(key=key, score=avg, samples=len(vals)))
        scored.sort(key=lambda c: c.score, reverse=higher_is_worse)
        return scored[:limit]

    # Explicit RL-facing helpers (no learning logic — reusable observation APIs)
    def observation_vector(self, profile: RuntimeProfile) -> dict[str, float]:
        return {
            "cpu_percent": float(profile.cpu.usage_percent),
            "wall_ms": float(profile.cpu.wall_time_ms),
            "rss_bytes": float(profile.memory.rss_bytes),
            "ipc": float(profile.hardware.ipc or profile.hardware.derived_ipc),
            "cache_misses": float(profile.hardware.cache_misses),
            "planner_ms": float(profile.planner.planner_time_ms),
            "execution_ms": float(profile.execution.execution_time_ms),
            "queue_ms": float(profile.planner.queue_time_ms),
            "spec_accept": float(profile.execution.speculative_acceptance_ratio),
        }

    def gepa_asi(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Actionable side information for GEPA — profiles only, no policy mutation."""
        out: list[dict[str, Any]] = []
        for p in self._profiles()[-limit:]:
            out.append(
                {
                    "profile_id": p.profile_id,
                    "backend": p.backend.backend,
                    "quantization": p.backend.quantization,
                    "observation": self.observation_vector(p),
                    "recommendations": list(p.recommendations),
                }
            )
        return out
