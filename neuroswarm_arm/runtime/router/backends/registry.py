"""Factory for pluggable vector backends."""

from __future__ import annotations

from typing import Any

from ..models import MetricKind
from ..turbovec_index import TurboVecIndex
from .exact import ExactNumpyIndex
from .faiss_backend import FaissIndex
from .hnsw_backend import HnswlibIndex
from .scann_backend import ScaNNIndex
from .sve_dot import SveDotIndex
from .usearch_backend import USearchIndex


def kernel_path_for(index: Any) -> str:
    """Honest kernel label for health/metrics (never claim SVE without real kernels)."""
    if hasattr(index, "kernel_path"):
        return str(getattr(index, "kernel_path"))
    name = str(getattr(index, "backend_name", "unknown"))
    if name == "turbovec":
        return "turbovec"
    if name in {"turbovec+exact", "exact"}:
        return "numpy"
    if name == "sve_dot":
        return "numpy_stub"
    return name


def build_vector_index(
    backend: str,
    dims: int,
    *,
    metric: MetricKind | str = MetricKind.COSINE,
    bit_width: int = 4,
    events: Any | None = None,
    turbovec_min_tools: int = 100,
):
    name = (backend or "turbovec").lower()
    metric_enum = metric if isinstance(metric, MetricKind) else MetricKind(str(metric).lower())
    if name in {"turbovec", "turbo", "default"}:
        return TurboVecIndex(
            dims,
            metric=metric_enum,
            bit_width=bit_width,
            events=events,
            min_tools_for_turbovec=turbovec_min_tools,
        )
    if name in {"exact", "numpy", "brute"}:
        return ExactNumpyIndex(dims, metric=metric_enum)
    if name in {"sve", "sve_dot", "svedot"}:
        return SveDotIndex(dims, metric=metric_enum)
    if name in {"faiss"}:
        return FaissIndex(dims, metric=metric_enum)
    if name in {"hnsw", "hnswlib"}:
        return HnswlibIndex(dims, metric=metric_enum)
    if name in {"usearch"}:
        return USearchIndex(dims, metric=metric_enum)
    if name in {"scann"}:
        return ScaNNIndex(dims, metric=metric_enum)
    # Unknown → TurboVec (which may itself fall back to exact)
    return TurboVecIndex(
        dims,
        metric=metric_enum,
        bit_width=bit_width,
        events=events,
        min_tools_for_turbovec=turbovec_min_tools,
    )
