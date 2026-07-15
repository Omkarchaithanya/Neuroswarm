"""ScaNN backend with exact fallback."""

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


class ScaNNIndex:
    """Optional ScaNN adapter. Falls back to exact numpy when scann unavailable."""

    def __init__(self, dims: int, metric: MetricKind = MetricKind.COSINE) -> None:
        self.dims = int(dims)
        self.metric = metric
        self._lock = threading.RLock()
        self._store = ExactNumpyIndex(dims, metric=metric)
        self._searcher: Any = None
        self._scann = None
        try:
            import scann  # type: ignore

            self._scann = scann
        except Exception:
            self._scann = None

    @property
    def backend_name(self) -> str:
        return "scann" if self._searcher is not None else "scann+exact"

    def _prep(self, vector: np.ndarray) -> np.ndarray:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if self.metric == MetricKind.COSINE:
            vec = l2_normalize(vec)
        return vec

    def _rebuild_searcher(self) -> None:
        self._searcher = None
        if self._scann is None:
            return
        keys = self._store.keys()
        if len(keys) < 2:
            return
        try:
            mat = np.asarray(self._store._matrix, dtype=np.float32)
            builder = self._scann.scann_ops_py.bind(
                mat,
                10,
                "dot_product" if self.metric != MetricKind.L2 else "squared_l2",
            )
            self._searcher = builder.score_brute_force().build()
        except Exception:
            self._searcher = None

    def insert(self, key: str, vector: np.ndarray) -> None:
        self.batch_insert([key], np.asarray(vector, dtype=np.float32).reshape(1, -1))

    def delete(self, key: str) -> bool:
        with self._lock:
            ok = self._store.delete(key)
            if ok:
                self._rebuild_searcher()
            return ok

    def update(self, key: str, vector: np.ndarray) -> None:
        with self._lock:
            self._store.update(key, self._prep(vector))
            self._rebuild_searcher()

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        prepared = np.stack([self._prep(v) for v in arr])
        with self._lock:
            self._store.batch_insert(keys, prepared)
            self._rebuild_searcher()

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
            keys = self._store.keys()
            if not keys:
                return []
            if self._searcher is not None:
                try:
                    idx, scores = self._searcher.search(q, min(k, len(keys)))
                    hits = []
                    for i, score in zip(idx, scores):
                        if int(i) < 0 or int(i) >= len(keys):
                            continue
                        hits.append(SearchHit(key=keys[int(i)], score=float(score), index=int(i)))
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
            (path / "scann_meta.json").write_text(
                json.dumps({"dims": self.dims, "metric": self.metric.value}),
                encoding="utf-8",
            )
            self._store.snapshot(path / "exact")

    def restore(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads((path / "scann_meta.json").read_text(encoding="utf-8"))
        with self._lock:
            self.dims = int(meta["dims"])
            self.metric = MetricKind(meta.get("metric", "cosine"))
            self._store = ExactNumpyIndex(self.dims, metric=self.metric)
            self._store.restore(path / "exact")
            self._rebuild_searcher()

    def compact(self) -> None:
        with self._lock:
            self._store.compact()
            self._rebuild_searcher()

    def size(self) -> int:
        return self._store.size()

    def keys(self) -> list[str]:
        return self._store.keys()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._searcher = None
