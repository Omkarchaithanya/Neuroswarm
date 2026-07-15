"""FAISS vector backend with exact fallback."""

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


class FaissIndex:
    def __init__(self, dims: int, metric: MetricKind = MetricKind.COSINE) -> None:
        self.dims = int(dims)
        self.metric = metric
        self._lock = threading.RLock()
        self._store = ExactNumpyIndex(dims, metric=metric)
        self._index: Any = None
        self._faiss = None
        try:
            import faiss  # type: ignore

            self._faiss = faiss
            self._index = self._new_index()
        except Exception:
            self._index = None

    def _new_index(self) -> Any:
        assert self._faiss is not None
        if self.metric == MetricKind.L2:
            return self._faiss.IndexFlatL2(self.dims)
        return self._faiss.IndexFlatIP(self.dims)

    @property
    def backend_name(self) -> str:
        return "faiss" if self._index is not None else "faiss+exact"

    def _prep(self, vector: np.ndarray) -> np.ndarray:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if self.metric == MetricKind.COSINE:
            vec = l2_normalize(vec)
        return vec

    def _sync_faiss(self) -> None:
        if self._faiss is None:
            self._index = None
            return
        self._index = self._new_index()
        keys = self._store.keys()
        if not keys:
            return
        mat = np.asarray(self._store._matrix, dtype=np.float32)
        if mat.shape[0]:
            self._index.add(mat)

    def insert(self, key: str, vector: np.ndarray) -> None:
        self.batch_insert([key], np.asarray(vector, dtype=np.float32).reshape(1, -1))

    def delete(self, key: str) -> bool:
        with self._lock:
            ok = self._store.delete(key)
            if ok:
                self._sync_faiss()
            return ok

    def update(self, key: str, vector: np.ndarray) -> None:
        with self._lock:
            self._store.update(key, self._prep(vector))
            self._sync_faiss()

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        prepared = np.stack([self._prep(v) for v in arr])
        with self._lock:
            self._store.batch_insert(keys, prepared)
            self._sync_faiss()

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
            if self._index is not None:
                try:
                    scores, idxs = self._index.search(q.reshape(1, -1), min(k, len(keys)))
                    hits = []
                    for score, idx in zip(scores[0], idxs[0]):
                        if idx < 0 or int(idx) >= len(keys):
                            continue
                        hits.append(SearchHit(key=keys[int(idx)], score=float(score), index=int(idx)))
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
            (path / "faiss_meta.json").write_text(
                json.dumps({"dims": self.dims, "metric": self.metric.value}),
                encoding="utf-8",
            )
            self._store.snapshot(path / "exact")
            if self._index is not None and self._faiss is not None:
                try:
                    self._faiss.write_index(self._index, str(path / "index.faiss"))
                except Exception:
                    pass

    def restore(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads((path / "faiss_meta.json").read_text(encoding="utf-8"))
        with self._lock:
            self.dims = int(meta["dims"])
            self.metric = MetricKind(meta.get("metric", "cosine"))
            self._store = ExactNumpyIndex(self.dims, metric=self.metric)
            self._store.restore(path / "exact")
            self._sync_faiss()

    def compact(self) -> None:
        with self._lock:
            self._store.compact()
            self._sync_faiss()

    def size(self) -> int:
        return self._store.size()

    def keys(self) -> list[str]:
        return self._store.keys()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._sync_faiss()
