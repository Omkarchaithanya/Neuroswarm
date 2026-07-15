"""Vector index protocol and backend registry."""

from __future__ import annotations

from .base import SearchHit, VectorIndex
from .exact import ExactNumpyIndex
from .faiss_backend import FaissIndex
from .hnsw_backend import HnswlibIndex
from .registry import build_vector_index
from .scann_backend import ScaNNIndex
from .usearch_backend import USearchIndex

__all__ = [
    "ExactNumpyIndex",
    "FaissIndex",
    "HnswlibIndex",
    "ScaNNIndex",
    "SearchHit",
    "USearchIndex",
    "VectorIndex",
    "build_vector_index",
]
