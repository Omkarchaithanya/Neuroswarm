"""Embedding service: BGE-small, MiniLM, ONNX INT8, hash fallback."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
from typing import Any, Iterator

import numpy as np

from .embedding_cache import EmbeddingCache
from .models import EmbeddingSpec
from .router_exceptions import EmbeddingError
from .router_metrics import RouterMetrics
from .similarity import l2_normalize, validate_embedding


KNOWN_MODELS = {
    "BAAI/bge-small-en-v1.5": 384,
    "bge-small-en-v1.5": 384,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
    "intfloat/e5-small-v2": 384,
    "e5-small-v2": 384,
}


def _hash_embed(text: str, dims: int) -> np.ndarray:
    vec = np.zeros(dims, dtype=np.float32)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    for i, ch in enumerate(text.lower()):
        vec[i % dims] += ((ord(ch) + digest[i % len(digest)]) % 31) / 31.0
    norm = float(np.linalg.norm(vec)) or 1.0
    return vec / norm


class EmbeddingService:
    def __init__(
        self,
        spec: EmbeddingSpec | None = None,
        *,
        cache: EmbeddingCache | None = None,
        metrics: RouterMetrics | None = None,
        workers: int = 2,
        fallback_dims: int = 64,
    ) -> None:
        self.spec = spec or EmbeddingSpec()
        self.cache = cache
        self.metrics = metrics
        self.fallback_dims = fallback_dims
        self._model: Any = None
        self._onnx: Any = None
        self._tokenizer: Any = None
        self._dims: int | None = KNOWN_MODELS.get(self.spec.model_name)
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="emb")
        self._backend = "hash"
        self._ensure_backend()

    @property
    def dims(self) -> int:
        return int(self._dims or self.spec.dims or self.fallback_dims)

    @property
    def backend_name(self) -> str:
        return self._backend

    def _ensure_backend(self) -> None:
        if self.spec.use_onnx:
            if self._try_onnx():
                return
        if self._try_sentence_transformers():
            return
        self._backend = "hash"
        self._dims = self._dims or self.fallback_dims

    def _try_sentence_transformers(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.spec.model_name, device="cpu")
            self._dims = int(self._model.get_sentence_embedding_dimension())
            self._backend = "sentence-transformers"
            return True
        except Exception:
            self._model = None
            return False

    def _try_onnx(self) -> bool:
        try:
            import onnxruntime as ort  # type: ignore

            path = self.spec.onnx_path
            if not path:
                return False
            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 2
            providers = ["CPUExecutionProvider"]
            self._onnx = ort.InferenceSession(path, sess_options=sess_options, providers=providers)
            # dims from model output
            out = self._onnx.get_outputs()[0]
            shape = out.shape
            self._dims = int(shape[-1]) if shape and isinstance(shape[-1], int) else self.spec.dims
            self._backend = "onnx-int8" if self.spec.use_int8 else "onnx"
            return True
        except Exception:
            self._onnx = None
            return False

    def encode(self, text: str, *, normalize: bool | None = None) -> np.ndarray:
        timer = self.metrics.timer() if self.metrics else None
        model_name = self.spec.model_name
        if self.cache is not None:
            cached = self.cache.get(model_name, text)
            if cached is not None:
                if self.metrics and timer:
                    self.metrics.set("router_embedding_latency_ms", timer.ms())
                return validate_embedding(cached, self.dims)
        vec = self._encode_uncached(text)
        do_norm = self.spec.normalize if normalize is None else normalize
        if do_norm:
            vec = l2_normalize(vec)
        vec = validate_embedding(vec, self.dims)
        if self.cache is not None:
            self.cache.set(model_name, text, vec)
        if self.metrics and timer:
            self.metrics.set("router_embedding_latency_ms", timer.ms())
        return vec

    def _encode_uncached(self, text: str) -> np.ndarray:
        if self._onnx is not None:
            return self._encode_onnx(text)
        if self._model is not None:
            arr = self._model.encode(text, normalize_embeddings=False)
            return np.asarray(arr, dtype=np.float32).reshape(-1)
        return _hash_embed(text, self.dims)

    def _encode_onnx(self, text: str) -> np.ndarray:
        # Minimal ONNX path: hash-bucket features if no tokenizer wired.
        # Production deployments should ship tokenizer + onnx model via NSA_ROUTER_ONNX_PATH.
        if self._tokenizer is not None:
            try:
                inputs = self._tokenizer(text, return_tensors="np", padding=True, truncation=True)
                feeds = {k: v for k, v in inputs.items()}
                outs = self._onnx.run(None, feeds)
                return np.asarray(outs[0], dtype=np.float32).reshape(-1)[: self.dims]
            except Exception as exc:
                raise EmbeddingError(f"onnx encode failed: {exc}") from exc
        # Deterministic projection from text into model dims for warm-path testing.
        return _hash_embed(text, self.dims)

    def encode_batch(self, texts: list[str], *, normalize: bool | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        if self._model is not None and self.cache is None:
            arr = self._model.encode(texts, normalize_embeddings=bool(normalize or self.spec.normalize))
            return np.asarray(arr, dtype=np.float32)
        rows = [self.encode(t, normalize=normalize) for t in texts]
        return np.stack(rows).astype(np.float32)

    async def encode_async(self, text: str, *, normalize: bool | None = None) -> np.ndarray:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: self.encode(text, normalize=normalize))

    def encode_stream(self, texts: Iterator[str], *, normalize: bool | None = None) -> Iterator[np.ndarray]:
        for text in texts:
            yield self.encode(text, normalize=normalize)

    def persist_stats(self) -> dict[str, Any]:
        return {
            "backend": self._backend,
            "model": self.spec.model_name,
            "dims": self.dims,
            "onnx": self.spec.use_onnx,
            "int8": self.spec.use_int8,
            "cache": self.cache.stats() if self.cache else None,
        }

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
