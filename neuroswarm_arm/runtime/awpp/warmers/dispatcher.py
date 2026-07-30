"""Budgeted warmer dispatcher — enforces Arm CPU fraction + rate limit."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Mapping, Sequence

from neuroswarm_arm.runtime.awpp.actions import WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.interfaces import IWarmer, PrewarmBudget, WarmResult
from neuroswarm_arm.runtime.awpp.metrics import AWPPMetrics


class WarmerDispatcher:
    """Dispatch warm targets under ``max_cpu_fraction`` of a rolling window."""

    def __init__(
        self,
        warmers: Mapping[str, IWarmer] | None = None,
        *,
        budget: PrewarmBudget | None = None,
        metrics: AWPPMetrics | None = None,
        window_s: float = 1.0,
    ) -> None:
        self.warmers = dict(warmers or {})
        self.budget = budget or PrewarmBudget(max_cpu_fraction=0.01)
        self.metrics = metrics
        self.window_s = window_s
        self._cpu_ms: deque[tuple[float, float]] = deque()
        self._rate_ts: deque[float] = deque()
        self.skips_total = 0
        self.warm_hits = 0
        self._inflight = 0

    def register(self, warmer: IWarmer) -> None:
        self.warmers[warmer.kind] = warmer

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_s
        while self._cpu_ms and self._cpu_ms[0][0] < cutoff:
            self._cpu_ms.popleft()
        while self._rate_ts and self._rate_ts[0] < cutoff:
            self._rate_ts.popleft()

    def cpu_fraction_used(self) -> float:
        now = time.monotonic()
        self._prune(now)
        used_ms = sum(ms for _, ms in self._cpu_ms)
        window_ms = max(1.0, self.window_s * 1000.0)
        return used_ms / window_ms

    def should_skip(self) -> bool:
        now = time.monotonic()
        self._prune(now)
        if self._inflight >= max(1, self.budget.max_concurrent):
            return True
        if self.cpu_fraction_used() >= self.budget.max_cpu_fraction:
            return True
        if len(self._rate_ts) >= max(1, int(self.budget.rate_limit_per_s)):
            return True
        return False

    async def dispatch(
        self,
        targets: Sequence[WarmTarget],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> list[WarmResult]:
        results: list[WarmResult] = []
        meta = dict(metadata or {})
        for target in targets:
            if self.should_skip():
                self.skips_total += 1
                if self.metrics is not None:
                    self.metrics.inc("awpp_budget_skips_total")
                results.append(
                    WarmResult(
                        target_kind=target.kind.value,
                        target_key=target.key,
                        success=False,
                        error="budget_skip",
                        metadata={"skipped": True},
                    )
                )
                continue
            warmer = self._resolve_warmer(target.kind)
            if warmer is None:
                results.append(
                    WarmResult(
                        target_kind=target.kind.value,
                        target_key=target.key,
                        success=False,
                        error="no_warmer",
                    )
                )
                continue
            self._inflight += 1
            self._rate_ts.append(time.monotonic())
            t0 = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    warmer.warm(target.key, metadata={**meta, **target.metadata}),
                    timeout=self.budget.timeout_s,
                )
            except Exception as exc:  # noqa: BLE001
                result = WarmResult(
                    target_kind=target.kind.value,
                    target_key=target.key,
                    success=False,
                    error=str(exc),
                )
            finally:
                self._inflight = max(0, self._inflight - 1)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            result.latency_ms = result.latency_ms or elapsed_ms
            self._cpu_ms.append((time.monotonic(), elapsed_ms))
            if self.metrics is not None:
                self.metrics.observe_warm(success=result.success, latency_ms=result.latency_ms)
                self.metrics.set(
                    "awpp_cpu_time_ms",
                    sum(ms for _, ms in self._cpu_ms),
                )
            if result.success:
                self.warm_hits += 1
            results.append(result)
        return results

    def _resolve_warmer(self, kind: WarmTargetKind | str) -> IWarmer | None:
        key = kind.value if isinstance(kind, WarmTargetKind) else str(kind)
        if key in self.warmers:
            return self.warmers[key]
        # Map related kinds
        aliases = {
            WarmTargetKind.QUANT.value: WarmTargetKind.MODEL.value,
            WarmTargetKind.BACKEND.value: WarmTargetKind.MODEL.value,
            WarmTargetKind.CASCADE.value: WarmTargetKind.MODEL.value,
            WarmTargetKind.CONTEXT.value: WarmTargetKind.MEMORY.value,
            WarmTargetKind.KV.value: WarmTargetKind.MEMORY.value,
        }
        mapped = aliases.get(key)
        return self.warmers.get(mapped) if mapped else None

    def status(self) -> dict[str, Any]:
        return {
            "cpu_fraction_used": self.cpu_fraction_used(),
            "max_cpu_fraction": self.budget.max_cpu_fraction,
            "skips_total": self.skips_total,
            "warm_hits": self.warm_hits,
            "inflight": self._inflight,
            "warmers": sorted(self.warmers.keys()),
        }
