"""Similarity scoring helpers (cosine / IP / L2)."""

from __future__ import annotations

import numpy as np

from .models import MetricKind


def l2_normalize(vectors: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        norm = float(np.linalg.norm(arr)) or eps
        return arr / norm
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, eps)
    return arr / norms


def validate_embedding(vector: np.ndarray, expected_dims: int | None = None) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32).reshape(-1)
    if not np.isfinite(arr).all():
        raise ValueError("embedding contains NaN/Inf")
    if expected_dims is not None and arr.shape[0] != expected_dims:
        raise ValueError(f"expected dims={expected_dims}, got {arr.shape[0]}")
    return arr


def cosine_scores(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = l2_normalize(query.reshape(1, -1))
    m = l2_normalize(matrix)
    return (m @ q.T).reshape(-1)


def ip_scores(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query.reshape(1, -1).astype(np.float32)
    return (matrix @ q.T).reshape(-1)


def l2_distances(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query.reshape(1, -1).astype(np.float32)
    # ||a-b||^2 = ||a||^2 + ||b||^2 - 2 a·b
    qq = np.sum(q * q, axis=1, keepdims=True)
    mm = np.sum(matrix * matrix, axis=1, keepdims=True).T
    dots = q @ matrix.T
    return np.sqrt(np.maximum(qq + mm - 2.0 * dots, 0.0)).reshape(-1)


def score_matrix(queries: np.ndarray, matrix: np.ndarray, metric: MetricKind) -> np.ndarray:
    q = np.asarray(queries, dtype=np.float32)
    m = np.asarray(matrix, dtype=np.float32)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    if metric == MetricKind.COSINE:
        qn = l2_normalize(q)
        mn = l2_normalize(m)
        return qn @ mn.T
    if metric == MetricKind.IP:
        return q @ m.T
    # L2 distance matrix (lower better)
    out = np.empty((q.shape[0], m.shape[0]), dtype=np.float32)
    for i in range(q.shape[0]):
        out[i] = l2_distances(q[i], m)
    return out


def keyword_overlap(query: str, text: str) -> float:
    q_tokens = {t for t in query.lower().split() if t}
    if not q_tokens:
        return 0.0
    t_tokens = set(text.lower().split())
    return len(q_tokens & t_tokens) / float(len(q_tokens))
