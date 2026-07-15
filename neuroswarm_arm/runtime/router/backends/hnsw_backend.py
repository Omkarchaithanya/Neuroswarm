"""HNSWlib backend with exact fallback."""

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


class HnswlibIndex:
    def __init__(self, dims: int, metric: MetricKind = MetricKind.COSINE, space: str | None = None) -> None:
        self.dims = int(dims)
        self.metric = metric
        self._lock = threading.RLock()
        self._store = ExactNumpyIndex(dims, metric=metric)
        self._index: Any = None
        self._hnswlib = None
        self._space = space or ("l2" if metric == MetricKind.L2 else "cosine")
        self._label = 0
        self._key_to_label: dict[str, int] = {}
        self._label_to_key: dict[int, str] = {}
        try:
            import hnswlib  # type: ignore

            self._hnswlib = hnswlib
            self._index = hnswlib.Index(space=self._space, dim=self.dims)
            self._index.init_index(max_elements=1024, ef_construction=200, M=16)
            self._index.set_ef(64)
        except Exception:
            self._index = None

    @property
    def backend_name(self) -> str:
        return "hnswlib" if self._index is not None else "hnswlib+exact"

    def _prep(self, vector: np.ndarray) -> np.ndarray:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if self.metric == MetricKind.COSINE:
            vec = l2_normalize(vec)
        return vec

    def insert(self, key: str, vector: np.ndarray) -> None:
        self.batch_insert([key], np.asarray(vector, dtype=np.float32).reshape(1, -1))

    def delete(self, key: str) -> bool:
        with self._lock:
            if key not in self._key_to_label:
                return False
            label = self._key_to_label.pop(key)
            self._label_to_key.pop(label, None)
            self._store.delete(key)
            if self._index is not None:
                try:
                    self._index.mark_deleted(label)
                except Exception:
                    pass
            return True

    def update(self, key: str, vector: np.ndarray) -> None:
        self.delete(key)
        self.insert(key, vector)

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        with self._lock:
            for key, raw in zip(keys, arr):
                vec = self._prep(raw)
                if key in self._key_to_label:
                    self.delete(key)
                label = self._label
                self._label += 1
                self._key_to_label[key] = label
                self._label_to_key[label] = key
                self._store.insert(key, vec)
                if self._index is not None:
                    try:
                        if self._index.get_current_count() >= self._index.get_max_elements():
                            self._index.resize_index(self._index.get_max_elements() * 2)
                        self._index.add_items(vec.reshape(1, -1), np.array([label]))
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
            if not self._key_to_label:
                return []
            if self._index is not None:
                try:
                    labels, dists = self._index.knn_query(q.reshape(1, -1), k=min(k, len(self._key_to_label)))
                    hits = []
                    for label, dist in zip(labels[0], dists[0]):
                        key = self._label_to_key.get(int(label))
                        if key is None:
                            continue
                        score = float(1.0 - dist) if self._space == "cosine" else float(-dist)
                        if self.metric == MetricKind.L2:
                            score = float(dist)
                        hits.append(SearchHit(key=key, score=score, index=int(label)))
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
            (path / "hnsw_meta.json").write_text(
                json.dumps(
                    {
                        "dims": self.dims,
                        "metric": self.metric.value,
                        "key_to_label": self._key_to_label,
                        "label": self._label,
                        "space": self._space,
                    }
                ),
                encoding="utf-8",
            )
            self._store.snapshot(path / "exact")
            if self._index is not None:
                try:
                    self._index.save_index(str(path / "index.hnsw"))
                except Exception:
                    pass

    def restore(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads((path / "hnsw_meta.json").read_text(encoding="utf-8"))
        with self._lock:
            self.dims = int(meta["dims"])
            self.metric = MetricKind(meta.get("metric", "cosine"))
            self._space = meta.get("space", self._space)
            self._key_to_label = {k: int(v) for k, v in meta["key_to_label"].items()}
            self._label_to_key = {int(v): k for k, v in self._key_to_label.items()}
            self._label = int(meta.get("label", 0))
            self._store = ExactNumpyIndex(self.dims, metric=self.metric)
            self._store.restore(path / "exact")
            if self._hnswlib is not None and (path / "index.hnsw").exists():
                try:
                    self._index = self._hnswlib.Index(space=self._space, dim=self.dims)
                    self._index.load_index(str(path / "index.hnsw"), max_elements=max(1024, len(self._key_to_label)))
                except Exception:
                    self._index = None

    def compact(self) -> None:
        self._store.compact()

    def size(self) -> int:
        return self._store.size()

    def keys(self) -> list[str]:
        return self._store.keys()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._key_to_label.clear()
            self._label_to_key.clear()
            self._label = 0
            if self._hnswlib is not None:
                self._index = self._hnswlib.Index(space=self._space, dim=self.dims)
                self._index.init_index(max_elements=1024, ef_construction=200, M=16)
