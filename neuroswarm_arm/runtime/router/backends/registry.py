"""Factory for pluggable vector backends."""

from __future__ import annotations

from typing import Any

from ..models import MetricKind
from ..turbovec_index import TurboVecIndex
from .exact import ExactNumpyIndex
from .faiss_backend import FaissIndex
from .hnsw_backend import HnswlibIndex
from .scann_backend import ScaNNIndex
from .usearch_backend import USearchIndex


def build_vector_index(
    backend: str,
    dims: int,
    *,
    metric: MetricKind | str = MetricKind.COSINE,
    bit_width: int = 4,
    events: Any | None = None,
):
    name = (backend or "turbovec").lower()
    metric_enum = metric if isinstance(metric, MetricKind) else MetricKind(str(metric).lower())
    if name in {"turbovec", "turbo", "default"}:
        return TurboVecIndex(dims, metric=metric_enum, bit_width=bit_width, events=events)
    if name in {"exact", "numpy", "brute"}:
        return ExactNumpyIndex(dims, metric=metric_enum)
    if name in {"faiss"}:
        return FaissIndex(dims, metric=metric_enum)
    if name in {"hnsw", "hnswlib"}:
        return HnswlibIndex(dims, metric=metric_enum)
    if name in {"usearch"}:
        return USearchIndex(dims, metric=metric_enum)
    if name in {"scann"}:
        return ScaNNIndex(dims, metric=metric_enum)
    # Unknown → TurboVec (which may itself fall back to exact)
    return TurboVecIndex(dims, metric=metric_enum, bit_width=bit_width, events=events)
