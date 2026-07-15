"""Quantization fallback dimension helpers."""

from __future__ import annotations

from .models import FallbackCandidate, FallbackDimension, ModelProfile

# Lower index = higher quality (typical GGUF ladder)
QUALITY_ORDER = (
    "F16",
    "Q8_0",
    "Q6_K",
    "Q5_K_M",
    "Q5_K_S",
    "Q4_K_M",
    "Q4_K_S",
    "Q4_0",
    "Q3_K_M",
    "Q2_K",
)


def quality_rank(quant: str) -> int:
    q = quant.upper()
    try:
        return QUALITY_ORDER.index(q)
    except ValueError:
        return len(QUALITY_ORDER)


def compatible_quants(
    profile: ModelProfile,
    preferences: list[str] | None = None,
) -> list[str]:
    supported = list(profile.quantizations)
    if not preferences:
        return sorted(supported, key=quality_rank)
    ordered: list[str] = []
    seen: set[str] = set()
    for pref in preferences:
        if pref in supported and pref not in seen:
            ordered.append(pref)
            seen.add(pref)
    for q in sorted(supported, key=quality_rank):
        if q not in seen:
            ordered.append(q)
            seen.add(q)
    return ordered


def quality_delta_for_quant(from_quant: str, to_quant: str) -> float:
    """Negative when degrading quality."""
    return float(quality_rank(from_quant) - quality_rank(to_quant)) * -0.05


def with_quant(candidate: FallbackCandidate, quant: str, *, from_quant: str) -> FallbackCandidate:
    dims = list(candidate.dimensions_changed)
    if FallbackDimension.QUANTIZATION not in dims:
        dims.append(FallbackDimension.QUANTIZATION)
    return candidate.model_copy(
        update={
            "quant": quant,
            "dimensions_changed": dims,
            "quality_delta": candidate.quality_delta + quality_delta_for_quant(from_quant, quant),
            "reason": f"{candidate.reason};quant={quant}".strip(";"),
        }
    )


def quant_supported(profile: ModelProfile, quant: str) -> bool:
    return quant in profile.quantizations
