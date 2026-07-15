"""Thread-count fallback dimension helpers."""

from __future__ import annotations

from .models import FallbackCandidate, FallbackDimension


def suggest_threads(
    available: int,
    current: int,
    preferences: list[str] | None = None,
) -> int:
    """Pick thread count ≤ available."""
    cap = max(1, available) if available > 0 else 1
    if preferences:
        prefs = sorted(
            (int(p) for p in preferences if str(p).lstrip("-").isdigit()),
            reverse=True,
        )
        for p in prefs:
            if 1 <= p <= cap:
                return p
    return min(current, cap) if current > 0 else cap


def with_threads(candidate: FallbackCandidate, thread_count: int) -> FallbackCandidate:
    dims = list(candidate.dimensions_changed)
    if FallbackDimension.THREAD_COUNT not in dims:
        dims.append(FallbackDimension.THREAD_COUNT)
    return candidate.model_copy(
        update={
            "thread_count": thread_count,
            "dimensions_changed": dims,
            "reason": f"{candidate.reason};threads={thread_count}".strip(";"),
        }
    )
