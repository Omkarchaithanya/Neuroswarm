"""TurboVec (TurboQuant) ANN adapter with exact numpy fallback."""

from __future__ import annotations

from pathlib import Path
import json
import threading
from typing import Any

import numpy as np

from .arm.alignment import aligned_float32
from .backends.base import SearchHit
from .backends.exact import ExactNumpyIndex
from .models import MetricKind
from .router_events import RouterEventBus, RouterEventKind
from .similarity import l2_normalize


class TurboVecIndex:
    """Default ANN backend for NEXUS-ARM Semantic MCP Tool Router.

    Uses turbovec.IdMapIndex when available (NEON/SIMD kernels on ARM).
    Falls back to ExactNumpyIndex with identical VectorIndex surface.
    """

    def __init__(
        self,
        dims: int,
        *,
        metric: MetricKind = MetricKind.COSINE,
        bit_width: int = 4,
        events: RouterEventBus | None = None,
    ) -> None:
        self.dims = int(dims)
        self.metric = metric
        self.bit_width = int(bit_width)
        self._events = events
        self._lock = threading.RLock()
        self._keys: list[str] = []
        self._key_to_id: dict[str, int] = {}
        self._id_to_key: dict[int, str] = {}
        self._next_id = 1
        self._vectors: dict[str, np.ndarray] = {}
        self._tv: Any = None
        self._fallback = ExactNumpyIndex(self.dims, metric=metric)
        self._using_turbovec = False
        self._init_turbovec()

    def _init_turbovec(self) -> None:
        try:
            from turbovec import IdMapIndex  # type: ignore

            self._tv = IdMapIndex(dim=self.dims, bit_width=self.bit_width)
            self._using_turbovec = True
        except Exception:
            self._tv = None
            self._using_turbovec = False
            if self._events is not None:
                self._events.emit(
                    RouterEventKind.BACKEND_FALLBACK,
                    from_backend="turbovec",
                    to_backend="exact",
                )

    @property
    def backend_name(self) -> str:
        return "turbovec" if self._using_turbovec else "turbovec+exact"

    @property
    def kernel_path(self) -> str:
        return "turbovec" if self._using_turbovec else "numpy"

    @property
    def sve_kernels_active(self) -> bool:
        return False

    def _prepare(self, vector: np.ndarray) -> np.ndarray:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dims:
            raise ValueError(f"dim mismatch: expected {self.dims}, got {vec.shape[0]}")
        if self.metric == MetricKind.COSINE:
            vec = l2_normalize(vec)
        return np.ascontiguousarray(vec, dtype=np.float32)

    def insert(self, key: str, vector: np.ndarray) -> None:
        self.batch_insert([key], np.asarray(vector, dtype=np.float32).reshape(1, -1))

    def delete(self, key: str) -> bool:
        with self._lock:
            if key not in self._key_to_id:
                return False
            uid = self._key_to_id.pop(key)
            self._id_to_key.pop(uid, None)
            self._vectors.pop(key, None)
            if key in self._keys:
                self._keys.remove(key)
            if self._using_turbovec and self._tv is not None:
                try:
                    self._tv.remove(np.uint64(uid))
                except Exception:
                    # Rebuild on remove failure
                    self._rebuild_turbovec()
            self._fallback.delete(key)
            return True

    def update(self, key: str, vector: np.ndarray) -> None:
        with self._lock:
            if key in self._key_to_id:
                self.delete(key)
            self.insert(key, vector)

    def batch_insert(self, keys: list[str], vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        prepared = aligned_float32((len(keys), self.dims))
        ids: list[int] = []
        with self._lock:
            for i, (key, raw) in enumerate(zip(keys, arr)):
                vec = self._prepare(raw)
                prepared[i] = vec
                if key in self._key_to_id:
                    self.delete(key)
                uid = self._next_id
                self._next_id += 1
                self._key_to_id[key] = uid
                self._id_to_key[uid] = key
                self._vectors[key] = vec
                self._keys.append(key)
                ids.append(uid)
                self._fallback.insert(key, vec)
            if self._using_turbovec and self._tv is not None and keys:
                try:
                    self._tv.add_with_ids(
                        prepared,
                        np.asarray(ids, dtype=np.uint64),
                    )
                except Exception:
                    self._using_turbovec = False
                    if self._events is not None:
                        self._events.emit(
                            RouterEventKind.BACKEND_FALLBACK,
                            from_backend="turbovec",
                            to_backend="exact",
                            reason="add_with_ids_failed",
                        )

    def _rebuild_turbovec(self) -> None:
        if not self._using_turbovec:
            return
        try:
            from turbovec import IdMapIndex  # type: ignore

            self._tv = IdMapIndex(dim=self.dims, bit_width=self.bit_width)
            if not self._keys:
                return
            mat = aligned_float32((len(self._keys), self.dims))
            ids = []
            for i, key in enumerate(self._keys):
                mat[i] = self._vectors[key]
                ids.append(self._key_to_id[key])
            self._tv.add_with_ids(mat, np.asarray(ids, dtype=np.uint64))
        except Exception:
            self._using_turbovec = False

    def search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self.ann_search(query, k)

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
        q = self._prepare(query)
        with self._lock:
            if not self._keys:
                return []
            if self._using_turbovec and self._tv is not None:
                try:
                    scores, ids = self._tv.search(q.reshape(1, -1), k=min(k, len(self._keys)))
                    hits: list[SearchHit] = []
                    for score, uid in zip(scores[0], ids[0]):
                        key = self._id_to_key.get(int(uid))
                        if key is None:
                            continue
                        hits.append(SearchHit(key=key, score=float(score), index=int(uid)))
                    if hits:
                        return hits
                except Exception:
                    pass
            return self._fallback.search(q, k)

    def exact_search(self, query: np.ndarray, k: int) -> list[SearchHit]:
        return self._fallback.exact_search(self._prepare(query), k)

    def snapshot(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        with self._lock:
            meta = {
                "dims": self.dims,
                "metric": self.metric.value,
                "bit_width": self.bit_width,
                "keys": self._keys,
                "key_to_id": self._key_to_id,
                "next_id": self._next_id,
                "backend": self.backend_name,
            }
            (path / "turbovec_meta.json").write_text(json.dumps(meta), encoding="utf-8")
            if self._keys:
                mat = np.stack([self._vectors[k] for k in self._keys]).astype(np.float32)
                np.save(path / "turbovec_vectors.npy", mat)
            if self._using_turbovec and self._tv is not None:
                try:
                    self._tv.write(str(path / "index.tvim"))
                except Exception:
                    pass
            self._fallback.snapshot(path / "exact")

    def restore(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads((path / "turbovec_meta.json").read_text(encoding="utf-8"))
        with self._lock:
            self.dims = int(meta["dims"])
            self.metric = MetricKind(meta.get("metric", "cosine"))
            self.bit_width = int(meta.get("bit_width", 4))
            self._keys = list(meta["keys"])
            self._key_to_id = {k: int(v) for k, v in meta["key_to_id"].items()}
            self._id_to_key = {int(v): k for k, v in self._key_to_id.items()}
            self._next_id = int(meta.get("next_id", 1))
            self._vectors = {}
            vec_path = path / "turbovec_vectors.npy"
            if vec_path.exists() and self._keys:
                mat = np.load(vec_path)
                for i, key in enumerate(self._keys):
                    self._vectors[key] = np.asarray(mat[i], dtype=np.float32)
            self._fallback = ExactNumpyIndex(self.dims, metric=self.metric)
            for key, vec in self._vectors.items():
                self._fallback.insert(key, vec)
            self._init_turbovec()
            tvim = path / "index.tvim"
            if self._using_turbovec and tvim.exists():
                try:
                    from turbovec import IdMapIndex  # type: ignore

                    self._tv = IdMapIndex.load(str(tvim))
                except Exception:
                    self._rebuild_turbovec()
            elif self._using_turbovec:
                self._rebuild_turbovec()

    def compact(self) -> None:
        with self._lock:
            self._fallback.compact()
            if self._using_turbovec:
                self._rebuild_turbovec()

    def size(self) -> int:
        with self._lock:
            return len(self._keys)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()
            self._key_to_id.clear()
            self._id_to_key.clear()
            self._vectors.clear()
            self._next_id = 1
            self._fallback.clear()
            self._init_turbovec()
