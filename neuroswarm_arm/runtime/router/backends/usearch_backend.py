"""USearch backend with exact fallback."""

from __future__ import annotations

from pathlib import Path
import json
import threading
from typing import Any

import numpy as np

from ..models import MetricKind
from ..similarity import l2_normalize
from .base import SearchHit
from .exact import ExactNumpyIndex


class USearchIndex:
    def __init__(self, dims: int, metric: MetricKind = MetricKind.COSINE) -> None:
        self.dims = int(dims)
        self.metric = metric
        self._lock = threading.RLock()
        self._store = ExactNumpyIndex(dims, metric=metric)
        self._index: Any = None
        self._keys: list[str] = []
        try:
            from usearch.index import Index  # type: ignore

            metric_name = "cos" if metric == MetricKind.COSINE else ("l2sq" if metric == MetricKind.L2 else "ip")
            self._index = Index(ndim=self.dims, metric=metric_name)
        except Exception:
            self._index = None

    @property
    def backend_name(self) -> str:
        return "usearch" if self._index is not None else "usearch+exact"

    def _prep(self, vector: np.ndarray) -> np.ndarray:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if self.metric == MetricKind.COSINE:
            vec = l2_normalize(vec)
        return vec

    def insert(self, key: str, vector: np.ndarray) -> None:
        self.batch_insert([key], np.asarray(vector, dtype=np.float32).reshape(1, -1))

    def delete(self, key: str) -> bool:
        with self._lock:
            if key not in self._keys:
                return False
            idx = self._keys.index(key)
            self._keys.pop(idx)
            self._store.delete(key)
            if self._index is not None:
                try:
                    self._index.remove(idx)
                except Exception:
                    self._rebuild()
            return True

    def update(self, key: str, vector: np.ndarray) -> None:
        self.delete(key)
        self.insert(key, vector)

    def _rebuild(self) -> None:
        if self._index is None:
            return
        try:
            from usearch.index import Index  # type: ignore

            metric_name = "cos" if self.metric == MetricKind.COSINE else (
                "l2sq" if self.metric == MetricKind.L2 else "ip"
            )
            self._index = Index(ndim=self.dims, metric=metric_name)
            for i, key in enumerate(self._keys):
                vec = self._store._matrix[self._store._key_to_row[key]]
                self._index.add(i, vec)
        except Exception:
            self._index = None

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        with self._lock:
            for key, raw in zip(keys, arr):
                vec = self._prep(raw)
                if key in self._keys:
                    self.delete(key)
                self._keys.append(key)
                self._store.insert(key, vec)
                if self._index is not None:
                    try:
                        self._index.add(len(self._keys) - 1, vec)
                    except Exception:
                        self._index = None

    def search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self.ann_search(query, k)

    def batch_search(self, queries: np.ndarray, k: int) -> list[list[SearchHit]]:
        q = np.asarray(queries, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        return [self.search(row, k) for row in q]

    def radius_search(self, query: np.ndarray, radius: float) -> list[SearchHit]:
        return self._store.radius_search(self._prep(query), radius)

    def ann_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        q = self._prep(query)
        with self._lock:
            if not self._keys:
                return []
            if self._index is not None:
                try:
                    matches = self._index.search(q, min(k, len(self._keys)))
                    hits = []
                    keys_attr = getattr(matches, "keys", None)
                    dists_attr = getattr(matches, "distances", None)
                    if keys_attr is not None and dists_attr is not None:
                        for idx, dist in zip(keys_attr, dists_attr):
                            i = int(idx)
                            if i < 0 or i >= len(self._keys):
                                continue
                            score = float(-dist) if self.metric != MetricKind.L2 else float(dist)
                            if self.metric == MetricKind.COSINE:
                                score = float(1.0 - dist)
                            hits.append(SearchHit(key=self._keys[i], score=score, index=i))
                    if hits:
                        return hits
                except Exception:
                    pass
            return self._store.search(q, k)

    def exact_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self._store.exact_search(self._prep(query), k)

    def snapshot(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        with self._lock:
            (path / "usearch_meta.json").write_text(
                json.dumps({"dims": self.dims, "metric": self.metric.value, "keys": self._keys}),
                encoding="utf-8",
            )
            self._store.snapshot(path / "exact")
            if self._index is not None:
                try:
                    self._index.save(str(path / "index.usearch"))
                except Exception:
                    pass

    def restore(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads((path / "usearch_meta.json").read_text(encoding="utf-8"))
        with self._lock:
            self.dims = int(meta["dims"])
            self.metric = MetricKind(meta.get("metric", "cosine"))
            self._keys = list(meta["keys"])
            self._store = ExactNumpyIndex(self.dims, metric=self.metric)
            self._store.restore(path / "exact")
            self._rebuild()

    def compact(self) -> None:
        with self._lock:
            self._store.compact()
            self._rebuild()

    def size(self) -> int:
        return self._store.size()

    def keys(self) -> list[str]:
        return list(self._keys)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()
            self._store.clear()
            self._rebuild()
