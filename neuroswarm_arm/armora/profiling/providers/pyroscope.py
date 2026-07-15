"""Pyroscope continuous-profiling sink — inactive until NSA_RPF_PYROSCOPE_URL set."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

from ..schemas import (
    CapabilityState,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)
from .base import BaseProfilerProvider, empty_batch, samples_from_mapping

logger = logging.getLogger(__name__)


class PyroscopeProfilerProvider(BaseProfilerProvider):
    name = "pyroscope"

    def __init__(self, *, url: str = "") -> None:
        super().__init__()
        self.url = (url or "").rstrip("/")

    def capabilities(self) -> ProviderCapabilities:
        ok = bool(self.url)
        return ProviderCapabilities(
            name=self.name,
            available=ok,
            state=CapabilityState.AVAILABLE if ok else CapabilityState.UNAVAILABLE,
            sampling=ok,
            tracing=False,
            cpu=ok,
            memory=False,
            hardware=False,
            continuous=ok,
            reasons=() if ok else ("NSA_RPF_PYROSCOPE_URL not configured",),
            extensions={"url": self.url},
        )

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        if not self.url:
            return empty_batch(self.name, session)
        try:
            req = urllib.request.Request(
                f"{self.url}/health",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                _ = resp.read()
            return samples_from_mapping(
                self.name,
                session,
                {"pyroscope.reachable": 1.0},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._mark_failure(exc)
            return empty_batch(self.name, session)
        except Exception as exc:
            self._mark_failure(exc)
            return empty_batch(self.name, session)
