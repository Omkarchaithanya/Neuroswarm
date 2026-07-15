"""Exact numpy ANN backend — SIMD-friendly float32 contiguous layout."""

from __future__ import annotations

from pathlib import Path
import json
import threading

import numpy as np

from ..arm.alignment import aligned_float32
from ..models import MetricKind
from ..similarity import score_matrix
from .base import SearchHit


class ExactNumpyIndex:
    """Production-ready exact search used as TurboVec/FAISS fallback."""

    def __init__(self, dims: int, metric: MetricKind = MetricKind.COSINE) -> None:
        self.dims = int(dims)
        self.metric = metric
        self._lock = threading.RLock()
        self._keys: list[str] = []
        self._key_to_row: dict[str, int] = {}
        self._matrix: np.ndarray = aligned_float32((0, self.dims))

    @property
    def backend_name(self) -> str:
        return "exact"

    def insert(self, key: str, vector: np.ndarray) -> None:
        self.batch_insert([key], np.asarray(vector, dtype=np.float32).reshape(1, -1))

    def delete(self, key: str) -> bool:
        with self._lock:
            row = self._key_to_row.pop(key, None)
            if row is None:
                return False
            self._keys.pop(row)
            self._matrix = np.delete(self._matrix, row, axis=0)
            self._key_to_row = {k: i for i, k in enumerate(self._keys)}
            return True

    def update(self, key: str, vector: np.ndarray) -> None:
        with self._lock:
            if key not in self._key_to_row:
                self.insert(key, vector)
                return
            row = self._key_to_row[key]
            vec = np.asarray(vector, dtype=np.float32).reshape(-1)
            if vec.shape[0] != self.dims:
                raise ValueError(f"dim mismatch: expected {self.dims}, got {vec.shape[0]}")
            self._matrix[row] = vec

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] != self.dims:
            raise ValueError(f"dim mismatch: expected {self.dims}, got {arr.shape[1]}")
        with self._lock:
            for key, vec in zip(keys, arr):
                if key in self._key_to_row:
                    self._matrix[self._key_to_row[key]] = vec
                else:
                    self._key_to_row[key] = len(self._keys)
                    self._keys.append(key)
                    if self._matrix.shape[0] == 0:
                        self._matrix = aligned_float32((1, self.dims))
                        self._matrix[0] = vec
                    else:
                        self._matrix = np.vstack([self._matrix, vec.reshape(1, -1)])

    def search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self.exact_search(query, k)

    def batch_search(self, queries: np.ndarray, k: int) -> list[list[SearchHit]]:
        q = np.asarray(queries, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        return [self.search(row, k) for row in q]

    def radius_search(self, query: np.ndarray, radius: float) -> list[SearchHit]:
        hits = self.exact_search(query, max(1, self.size()))
        if self.metric == MetricKind.L2:
            return [h for h in hits if h.score <= radius]
        return [h for h in hits if h.score >= radius]

    def ann_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self.exact_search(query, k)

    def exact_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        with self._lock:
            if not self._keys:
                return []
            q = np.asarray(query, dtype=np.float32).reshape(1, -1)
            scores = score_matrix(q, self._matrix, self.metric)[0]
            k_eff = min(int(k), len(self._keys))
            if self.metric == MetricKind.L2:
                idx = np.argpartition(scores, k_eff - 1)[:k_eff]
                idx = idx[np.argsort(scores[idx])]
            else:
                idx = np.argpartition(-scores, k_eff - 1)[:k_eff]
                idx = idx[np.argsort(-scores[idx])]
            return [
                SearchHit(key=self._keys[int(i)], score=float(scores[int(i)]), index=int(i))
                for i in idx
            ]

    def snapshot(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        with self._lock:
            np.save(path / "matrix.npy", self._matrix)
            (path / "meta.json").write_text(
                json.dumps({"keys": self._keys, "dims": self.dims, "metric": self.metric.value}),
                encoding="utf-8",
            )

    def restore(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        matrix = np.load(path / "matrix.npy")
        with self._lock:
            self.dims = int(meta["dims"])
            self.metric = MetricKind(meta.get("metric", "cosine"))
            self._keys = list(meta["keys"])
            self._matrix = np.asarray(matrix, dtype=np.float32)
            self._key_to_row = {k: i for i, k in enumerate(self._keys)}

    def compact(self) -> None:
        with self._lock:
            if self._matrix.size == 0:
                return
            self._matrix = np.ascontiguousarray(self._matrix, dtype=np.float32)

    def size(self) -> int:
        with self._lock:
            return len(self._keys)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()
            self._key_to_row.clear()
            self._matrix = aligned_float32((0, self.dims))
