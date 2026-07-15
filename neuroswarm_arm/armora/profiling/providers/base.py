"""Shared provider helpers — capability detection never raises."""

from __future__ import annotations

import logging
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from ..schemas import (
    CapabilityState,
    MetricBatch,
    MetricSample,
    ProfileSessionContext,
    ProviderCapabilities,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


def detect_cpu_flags() -> set[str]:
    flags: set[str] = set()
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return flags
    try:
        text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return flags
    for flag in ("sve2", "i8mm", "sve", "asimd", "dotprod", "bf16"):
        if f" {flag}" in f" {text}" or f"\t{flag}" in text or flag in text.split():
            flags.add(flag)
    return flags


def which_binary(name: str) -> str | None:
    return shutil.which(name)


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def empty_batch(provider: str, session: ProfileSessionContext) -> MetricBatch:
    return MetricBatch(samples=[], provider=provider, session_id=session.session_id)


def samples_from_mapping(
    provider: str,
    session: ProfileSessionContext,
    values: dict[str, float],
    *,
    unit: str = "",
) -> MetricBatch:
    return MetricBatch(
        provider=provider,
        session_id=session.session_id,
        samples=[
            MetricSample(name=k, value=float(v), unit=unit, labels={"provider": provider})
            for k, v in values.items()
        ],
    )


class BaseProfilerProvider:
    """Concrete base with failure-safe defaults."""

    name: str = "base"

    def __init__(self) -> None:
        self._failures = 0
        self._initialized = False
        self._last_error = ""

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            available=False,
            state=CapabilityState.UNAVAILABLE,
        )

    def initialize(self) -> None:
        self._initialized = True

    def start(self, session: ProfileSessionContext) -> None:
        del session

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        return empty_batch(self.name, session)

    def stop(self, session: ProfileSessionContext) -> MetricBatch:
        return self.sample(session)

    def shutdown(self) -> None:
        self._initialized = False

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            healthy=self._failures == 0 and self.capabilities().available,
            message=self._last_error,
            failures=self._failures,
        )

    def _mark_failure(self, exc: BaseException) -> None:
        self._failures += 1
        self._last_error = str(exc)
        logger.warning("rpf provider %s failure: %s", self.name, exc)


def env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in {"0", "false", "False", "no", "NO"}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default
