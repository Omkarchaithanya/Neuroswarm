"""SVE-path VectorIndex stub — delegates to ExactNumpyIndex until real SVE kernels land.

Do not claim SVE2 utilization or speedups; kernel_path stays ``numpy_stub``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..models import MetricKind
from .base import SearchHit
from .exact import ExactNumpyIndex


class SveDotIndex:
    """Extension-point ANN backend labeled for future SVE SDOT kernels.

    Today this is an exact numpy matmul path with the same ``VectorIndex`` surface.
    ``nexus_hw_sve2_utilization`` must remain 0 while ``kernel_path == numpy_stub``.
    """

    def __init__(self, dims: int, metric: MetricKind = MetricKind.COSINE) -> None:
        self.dims = int(dims)
        self.metric = metric
        self._inner = ExactNumpyIndex(dims, metric=metric)
        self.kernel_path = "numpy_stub"
        self.sve_kernels_active = False

    @property
    def backend_name(self) -> str:
        return "sve_dot"

    def insert(self, key: str, vector: np.ndarray) -> None:
        self._inner.insert(key, vector)

    def delete(self, key: str) -> bool:
        return self._inner.delete(key)

    def update(self, key: str, vector: np.ndarray) -> None:
        self._inner.update(key, vector)

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        self._inner.batch_insert(keys, vectors)

    def search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self._inner.search(query, k)

    def batch_search(self, queries: np.ndarray, k: int) -> list[list[SearchHit]]:
        return self._inner.batch_search(queries, k)

    def radius_search(self, query: np.ndarray, radius: float) -> list[SearchHit]:
        return self._inner.radius_search(query, radius)

    def ann_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self._inner.ann_search(query, k)

    def exact_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self._inner.exact_search(query, k)

    def snapshot(self, path: Path) -> None:
        self._inner.snapshot(path)

    def restore(self, path: Path) -> None:
        self._inner.restore(path)

    def compact(self) -> None:
        self._inner.compact()

    def size(self) -> int:
        return self._inner.size()

    def keys(self) -> list[str]:
        return self._inner.keys()

    def clear(self) -> None:
        self._inner.clear()
