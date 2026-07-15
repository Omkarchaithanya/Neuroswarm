"""Fallback dimension + cascade strategy tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import (
    CascadeStrategy,
    FallbackDimension,
    FallbackDimensionConfig,
    default_dimension_configs,
    enabled_dimensions,
    resolve_cascade_strategy,
)


def test_default_all_dimensions_enabled():
    configs = default_dimension_configs()
    assert len(configs) == 8
    assert enabled_dimensions(configs) == [
        FallbackDimension.MODEL_TIER,
        FallbackDimension.BACKEND,
        FallbackDimension.QUANTIZATION,
        FallbackDimension.CONTEXT_LENGTH,
        FallbackDimension.THREAD_COUNT,
        FallbackDimension.REASONING_BUDGET,
        FallbackDimension.TOOL_USAGE,
        FallbackDimension.CASCADE,
    ]


def test_disable_dimension():
    configs = [
        FallbackDimensionConfig(dimension=FallbackDimension.MODEL_TIER, enabled=True),
        FallbackDimensionConfig(dimension=FallbackDimension.BACKEND, enabled=False),
    ]
    assert enabled_dimensions(configs) == [FallbackDimension.MODEL_TIER]


def test_resolve_cascade_strategy():
    assert resolve_cascade_strategy(None) == CascadeStrategy.SEQUENTIAL
    assert resolve_cascade_strategy("least_degradation") == CascadeStrategy.LEAST_DEGRADATION
    assert (
        resolve_cascade_strategy(CascadeStrategy.PARALLEL_SCORE)
        == CascadeStrategy.PARALLEL_SCORE
    )
