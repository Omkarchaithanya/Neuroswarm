"""Lightweight profiler hooks for scheduling / task spans."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from threading import Lock


@dataclass
class ProfileSample:
    name: str
    duration_ms: float
    ts: float


class Profiler:
    def __init__(self, max_samples: int = 2048) -> None:
        self._max = max_samples
        self._samples: list[ProfileSample] = []
        self._lock = Lock()

    def record(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._samples.append(
                ProfileSample(name=name, duration_ms=duration_ms, ts=monotonic())
            )
            if len(self._samples) > self._max:
                self._samples = self._samples[-self._max // 2 :]

    def span(self, name: str):
        return _ProfileSpan(self, name)

    def last(self, name: str | None = None) -> ProfileSample | None:
        with self._lock:
            if not self._samples:
                return None
            if name is None:
                return self._samples[-1]
            for sample in reversed(self._samples):
                if sample.name == name:
                    return sample
            return None

    def summary(self) -> dict[str, float]:
        with self._lock:
            if not self._samples:
                return {}
            by: dict[str, list[float]] = {}
            for s in self._samples:
                by.setdefault(s.name, []).append(s.duration_ms)
            return {k: sum(v) / len(v) for k, v in by.items()}


class _ProfileSpan:
    def __init__(self, profiler: Profiler, name: str) -> None:
        self._profiler = profiler
        self._name = name
        self._start = 0.0

    def __enter__(self) -> _ProfileSpan:
        self._start = monotonic()
        return self

    def __exit__(self, *exc: object) -> None:
        self._profiler.record(self._name, (monotonic() - self._start) * 1000.0)


# tracing.py re-export alias
from .opentelemetry import OpenTelemetryAdapter as TracerAdapter  # noqa: E402
