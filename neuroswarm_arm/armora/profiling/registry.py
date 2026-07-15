"""Capability detection + provider selection + FailureIsolatingProxy."""

from __future__ import annotations

import logging
from typing import Any

from .config import RPFRuntimeConfig
from .providers import (
    EbpfProfilerProvider,
    MockProfilerProvider,
    ParcaProfilerProvider,
    PerfProfilerProvider,
    PerformixProfilerProvider,
    PsutilProfilerProvider,
    PyroscopeProfilerProvider,
)
from .schemas import (
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
    ProviderHealth,
)

logger = logging.getLogger(__name__)

# Cascade order for auto selection (Performix → perf → psutil → mock)
_AUTO_CASCADE = ("performix", "perf", "psutil", "mock")


class FailureIsolatingProxy:
    """Wrap primary provider; on failure demote through fallbacks without raising."""

    def __init__(
        self,
        primary: Any,
        fallbacks: list[Any],
        *,
        max_failures: int = 3,
    ) -> None:
        self._primary = primary
        self._fallbacks = list(fallbacks)
        self._active = primary
        self._max_failures = max_failures
        self._failures = 0
        self._demotions = 0

    @property
    def name(self) -> str:
        return str(getattr(self._active, "name", "unknown"))

    def capabilities(self) -> ProviderCapabilities:
        try:
            return self._active.capabilities()
        except Exception as exc:
            logger.warning("rpf capabilities failed: %s", exc)
            return MockProfilerProvider().capabilities()

    def initialize(self) -> None:
        try:
            self._active.initialize()
        except Exception as exc:
            self._handle_failure(exc)
            try:
                self._active.initialize()
            except Exception:
                pass

    def start(self, session: ProfileSessionContext) -> None:
        try:
            self._active.start(session)
        except Exception as exc:
            self._handle_failure(exc)
            try:
                self._active.start(session)
            except Exception:
                pass

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        try:
            return self._active.sample(session)
        except Exception as exc:
            self._handle_failure(exc)
            try:
                return self._active.sample(session)
            except Exception as exc2:
                logger.warning("rpf sample fallback failed: %s", exc2)
                return MetricBatch(
                    samples=[],
                    provider=self.name,
                    session_id=session.session_id,
                )

    def stop(self, session: ProfileSessionContext) -> MetricBatch:
        try:
            return self._active.stop(session)
        except Exception as exc:
            self._handle_failure(exc)
            try:
                return self._active.stop(session)
            except Exception:
                return MetricBatch(
                    samples=[],
                    provider=self.name,
                    session_id=session.session_id,
                )

    def shutdown(self) -> None:
        for p in [self._primary, *self._fallbacks]:
            try:
                p.shutdown()
            except Exception:
                pass

    def health(self) -> ProviderHealth:
        try:
            h = self._active.health()
            return ProviderHealth(
                name=h.name,
                healthy=h.healthy and self._failures < self._max_failures,
                message=h.message,
                failures=self._failures + self._demotions,
            )
        except Exception:
            return ProviderHealth(name=self.name, healthy=False, failures=self._failures)

    def recommendations(self) -> list[str]:
        fn = getattr(self._active, "recommendations", None)
        if callable(fn):
            try:
                return list(fn())
            except Exception:
                return []
        return []

    def _handle_failure(self, exc: BaseException) -> None:
        self._failures += 1
        logger.warning(
            "rpf provider %s failed (%s); demoting if possible",
            getattr(self._active, "name", "?"),
            exc,
        )
        if self._failures >= self._max_failures and self._fallbacks:
            nxt = self._fallbacks.pop(0)
            self._active = nxt
            self._demotions += 1
            self._failures = 0
            logger.warning("rpf switched provider to %s", getattr(nxt, "name", "?"))


class ProfilerRegistry:
    """Build and select profiler providers from config."""

    def __init__(self, cfg: RPFRuntimeConfig) -> None:
        self.cfg = cfg
        self._providers: dict[str, Any] = {}
        self._build_all()

    def _build_all(self) -> None:
        self._providers["mock"] = MockProfilerProvider()
        self._providers["psutil"] = PsutilProfilerProvider()
        self._providers["perf"] = PerfProfilerProvider()
        self._providers["performix"] = PerformixProfilerProvider(
            binary=self.cfg.performix_binary,
            recipe=self.cfg.performix_recipe,
            output_dir=self.cfg.work_dir / "performix",
            enabled=self.cfg.allow_performix,
        )
        self._providers["ebpf"] = EbpfProfilerProvider()
        self._providers["parca"] = ParcaProfilerProvider(url=self.cfg.parca_url)
        self._providers["pyroscope"] = PyroscopeProfilerProvider(url=self.cfg.pyroscope_url)

    def all_capabilities(self) -> dict[str, ProviderCapabilities]:
        out: dict[str, ProviderCapabilities] = {}
        for name, prov in self._providers.items():
            try:
                out[name] = prov.capabilities()
            except Exception as exc:
                logger.warning("rpf capability probe failed for %s: %s", name, exc)
                out[name] = ProviderCapabilities(name=name, available=False)
        return out

    def select(self) -> FailureIsolatingProxy:
        if not self.cfg.enabled or self.cfg.mode.value == "disabled":
            mock = self._providers["mock"]
            return FailureIsolatingProxy(mock, [], max_failures=self.cfg.max_provider_failures)

        chosen_name = self.cfg.provider
        if chosen_name == "auto":
            chosen_name = self._auto_select()
        elif chosen_name not in self._providers:
            logger.warning("rpf unknown provider %s; using auto", chosen_name)
            chosen_name = self._auto_select()

        primary = self._providers.get(chosen_name) or self._providers["mock"]
        if not primary.capabilities().available:
            chosen_name = self._auto_select()
            primary = self._providers[chosen_name]

        fallbacks: list[Any] = []
        for name in ("psutil", "mock"):
            if name == getattr(primary, "name", ""):
                continue
            p = self._providers[name]
            if p.capabilities().available or name == "mock":
                fallbacks.append(p)
        return FailureIsolatingProxy(
            primary,
            fallbacks,
            max_failures=self.cfg.max_provider_failures,
        )

    def _auto_select(self) -> str:
        for name in _AUTO_CASCADE:
            if name == "performix" and not self.cfg.allow_performix:
                continue
            prov = self._providers.get(name)
            if prov is None:
                continue
            try:
                if prov.capabilities().available:
                    return name
            except Exception:
                continue
        return "mock"

    def get(self, name: str) -> Any | None:
        return self._providers.get(name)
