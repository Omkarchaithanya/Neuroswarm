"""Fallback dimension configuration and cascade strategy helpers."""

from __future__ import annotations

from .models import CascadeStrategy, FallbackDimension, FallbackDimensionConfig


DEFAULT_DIMENSIONS: tuple[FallbackDimension, ...] = (
    FallbackDimension.MODEL_TIER,
    FallbackDimension.BACKEND,
    FallbackDimension.QUANTIZATION,
    FallbackDimension.CONTEXT_LENGTH,
    FallbackDimension.THREAD_COUNT,
    FallbackDimension.REASONING_BUDGET,
    FallbackDimension.TOOL_USAGE,
    FallbackDimension.CASCADE,
)


def default_dimension_configs() -> list[FallbackDimensionConfig]:
    """Independent per-dimension defaults — all enabled."""
    return [
        FallbackDimensionConfig(dimension=d, enabled=True) for d in DEFAULT_DIMENSIONS
    ]


def enabled_dimensions(
    configs: list[FallbackDimensionConfig] | None,
) -> list[FallbackDimension]:
    if not configs:
        return list(DEFAULT_DIMENSIONS)
    return [c.dimension for c in configs if c.enabled]


def config_for(
    configs: list[FallbackDimensionConfig],
    dimension: FallbackDimension,
) -> FallbackDimensionConfig | None:
    for c in configs:
        if c.dimension == dimension:
            return c
    return None


def resolve_cascade_strategy(name: str | CascadeStrategy | None) -> CascadeStrategy:
    if name is None:
        return CascadeStrategy.SEQUENTIAL
    if isinstance(name, CascadeStrategy):
        return name
    return CascadeStrategy(str(name).strip().lower())
