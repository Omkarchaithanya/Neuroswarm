"""Context-length fallback dimension helpers."""

from __future__ import annotations

from .models import FallbackCandidate, FallbackDimension, ModelProfile


def context_fits(profile: ModelProfile, tokens_needed: int) -> bool:
    return profile.context_length >= tokens_needed


def suggest_context(
    profile: ModelProfile,
    tokens_needed: int,
    preferences: list[str] | None = None,
) -> int:
    """Pick largest preferred context ≤ profile max that still fits need."""
    max_ctx = profile.context_length
    if preferences:
        prefs = sorted(
            (int(p) for p in preferences if str(p).isdigit()),
            reverse=True,
        )
        for p in prefs:
            if p <= max_ctx and p >= tokens_needed:
                return p
    if tokens_needed <= max_ctx:
        return max(tokens_needed, min(max_ctx, max(tokens_needed, 2048)))
    return max_ctx


def with_context(candidate: FallbackCandidate, context_length: int) -> FallbackCandidate:
    dims = list(candidate.dimensions_changed)
    if FallbackDimension.CONTEXT_LENGTH not in dims:
        dims.append(FallbackDimension.CONTEXT_LENGTH)
    return candidate.model_copy(
        update={
            "context_length": context_length,
            "dimensions_changed": dims,
            "reason": f"{candidate.reason};context={context_length}".strip(";"),
        }
    )
