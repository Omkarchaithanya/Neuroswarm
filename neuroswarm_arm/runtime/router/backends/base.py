"""Pluggable VectorIndex protocol for ANN backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from ..models import MetricKind


@dataclass(slots=True)
class SearchHit:
    key: str
    score: float
    index: int = -1


@runtime_checkable
class VectorIndex(Protocol):
    metric: MetricKind
    dims: int

    def insert(self, key: str, vector: np.ndarray) -> None: ...

    def delete(self, key: str) -> bool: ...

    def update(self, key: str, vector: np.ndarray) -> None: ...

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None: ...

    def search(self, query: np.ndarray, k: int) -> list[SearchHit]: ...

    def batch_search(self, queries: np.ndarray, k: int) -> list[list[SearchHit]]: ...

    def radius_search(self, query: np.ndarray, radius: float) -> list[SearchHit]: ...

    def ann_search(self, query: np.ndarray, k: int) -> list[SearchHit]: ...

    def exact_search(self, query: np.ndarray, k: int) -> list[SearchHit]: ...

    def snapshot(self, path: Path) -> None: ...

    def restore(self, path: Path) -> None: ...

    def compact(self) -> None: ...

    def size(self) -> int: ...

    def keys(self) -> list[str]: ...

    def clear(self) -> None: ...

    @property
    def backend_name(self) -> str: ...
