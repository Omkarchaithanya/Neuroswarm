"""Hash embeddings — emergency JSON provider ONLY.

Production Mem0 path owns embeddings via configured embedder.
Do not use hash_embed as a Mem0 substitute.
"""

from __future__ import annotations

import hashlib
import math
from typing import Sequence


def hash_embed(text: str, *, dims: int = 64) -> list[float]:
    """Deterministic bag-of-hashes for JsonEmergencyFallback ranking only."""
    vec = [0.0] * dims
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return float(dot / (na * nb))
