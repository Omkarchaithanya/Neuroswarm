"""Sampling strategies — AlwaysOn/Off, Head, Tail, Adaptive, Dynamic."""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Mapping

from .config import ROFRuntimeConfig
from .schemas import AttributeKeys, SamplingDecision


class AlwaysOnSampler:
    name = "always_on"

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision:
        del name, attributes, parent_sampled
        return SamplingDecision(sampled=True, reason="always_on")


class AlwaysOffSampler:
    name = "always_off"

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision:
        del name, parent_sampled
        if _force_sample(attributes):
            return SamplingDecision(sampled=True, reason="force", force=True)
        return SamplingDecision(sampled=False, reason="always_off")


class HeadRatioSampler:
    name = "head"

    def __init__(self, ratio: float = 0.1) -> None:
        self.ratio = max(0.0, min(1.0, float(ratio)))

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision:
        del name
        if parent_sampled is True:
            return SamplingDecision(sampled=True, reason="parent")
        if _force_sample(attributes):
            return SamplingDecision(sampled=True, reason="force", force=True)
        ok = random.random() < self.ratio
        return SamplingDecision(sampled=ok, reason=f"head:{self.ratio}")


class TailSampler:
    """Buffer decision deferred to span end based on error / latency."""

    name = "tail"

    def __init__(self, latency_ms_threshold: float = 1500.0) -> None:
        self.latency_ms_threshold = float(latency_ms_threshold)
        self._pending: dict[str, bool] = {}
        self._lock = threading.Lock()

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision:
        del name, parent_sampled
        # Optimistic sample; finalize may drop via processor
        if _force_sample(attributes):
            return SamplingDecision(sampled=True, reason="force", force=True)
        return SamplingDecision(sampled=True, reason="tail_pending")

    def finalize(
        self,
        *,
        attributes: Mapping[str, Any] | None = None,
        latency_ms: float = 0.0,
        error: bool = False,
    ) -> SamplingDecision:
        if error or _force_sample(attributes) or latency_ms >= self.latency_ms_threshold:
            return SamplingDecision(sampled=True, reason="tail_keep")
        return SamplingDecision(sampled=False, reason="tail_drop")


class AdaptiveSampler:
    """Raise sample rate when error-rate or latency SLO breached."""

    name = "adaptive"

    def __init__(
        self,
        *,
        base_ratio: float = 0.1,
        error_rate_threshold: float = 0.05,
        latency_ms_threshold: float = 2000.0,
    ) -> None:
        self.base_ratio = base_ratio
        self.error_rate_threshold = error_rate_threshold
        self.latency_ms_threshold = latency_ms_threshold
        self._lock = threading.Lock()
        self._total = 0
        self._errors = 0
        self._latencies: list[float] = []
        self._window_start = time.monotonic()

    def record_outcome(self, *, error: bool = False, latency_ms: float = 0.0) -> None:
        with self._lock:
            self._total += 1
            if error:
                self._errors += 1
            if latency_ms > 0:
                self._latencies.append(latency_ms)
                if len(self._latencies) > 256:
                    self._latencies = self._latencies[-128:]

    def _current_ratio(self) -> float:
        with self._lock:
            if self._total == 0:
                return self.base_ratio
            err_rate = self._errors / max(self._total, 1)
            p99 = sorted(self._latencies)[int(0.99 * (len(self._latencies) - 1))] if self._latencies else 0.0
            if err_rate >= self.error_rate_threshold or p99 >= self.latency_ms_threshold:
                return min(1.0, self.base_ratio * 4.0)
            return self.base_ratio

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision:
        del name
        if parent_sampled is True:
            return SamplingDecision(sampled=True, reason="parent")
        if _force_sample(attributes):
            return SamplingDecision(sampled=True, reason="force", force=True)
        ratio = self._current_ratio()
        ok = random.random() < ratio
        return SamplingDecision(sampled=ok, reason=f"adaptive:{ratio:.3f}")


class DynamicSampler:
    """Hot-reload wrapper around config-selected sampler."""

    name = "dynamic"

    def __init__(self, config: ROFRuntimeConfig) -> None:
        self.config = config
        self._inner = build_sampler(config)
        self._lock = threading.Lock()

    def reload(self, config: ROFRuntimeConfig | None = None) -> None:
        with self._lock:
            if config is not None:
                self.config = config
            self._inner = build_sampler(self.config)

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision:
        with self._lock:
            inner = self._inner
        return inner.should_sample(name=name, attributes=attributes, parent_sampled=parent_sampled)


def _force_sample(attributes: Mapping[str, Any] | None) -> bool:
    if not attributes:
        return False
    if attributes.get(AttributeKeys.FORCE_SAMPLE) in (True, "1", "true", 1):
        return True
    if attributes.get(AttributeKeys.ERROR):
        return True
    outcome = str(attributes.get(AttributeKeys.OUTCOME, "")).lower()
    return outcome in {"error", "budget_exceeded", "backend_failure"}


def build_sampler(config: ROFRuntimeConfig) -> Any:
    name = (config.sampler or "always_on").lower()
    if name in {"always_on", "alwayson", "on"}:
        return AlwaysOnSampler()
    if name in {"always_off", "alwaysoff", "off"}:
        return AlwaysOffSampler()
    if name in {"head", "head_ratio"}:
        return HeadRatioSampler(config.head_ratio)
    if name == "tail":
        return TailSampler(config.tail_latency_ms_threshold)
    if name == "adaptive":
        return AdaptiveSampler(
            base_ratio=config.head_ratio,
            error_rate_threshold=config.adaptive_error_rate_threshold,
            latency_ms_threshold=config.adaptive_latency_ms_threshold,
        )
    if name == "dynamic":
        return DynamicSampler(config)
    return AlwaysOnSampler()
