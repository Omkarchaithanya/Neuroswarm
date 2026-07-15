"""Backend fallback dimension helpers."""

from __future__ import annotations

from .models import FallbackCandidate, FallbackDimension, ModelProfile


def compatible_backends(
    profile: ModelProfile,
    preferences: list[str] | None = None,
) -> list[str]:
    """Ordered backends: preferences ∩ supported, then remaining supported."""
    supported = list(profile.supported_backends)
    if not preferences:
        return supported
    ordered: list[str] = []
    seen: set[str] = set()
    for pref in preferences:
        if pref in supported and pref not in seen:
            ordered.append(pref)
            seen.add(pref)
    for b in supported:
        if b not in seen:
            ordered.append(b)
            seen.add(b)
    return ordered


def with_backend(candidate: FallbackCandidate, backend: str) -> FallbackCandidate:
    dims = list(candidate.dimensions_changed)
    if FallbackDimension.BACKEND not in dims:
        dims.append(FallbackDimension.BACKEND)
    return candidate.model_copy(
        update={
            "backend": backend,
            "dimensions_changed": dims,
            "reason": f"{candidate.reason};backend={backend}".strip(";"),
        }
    )


def backend_compatible(profile: ModelProfile, backend: str) -> bool:
    return backend in profile.supported_backends
