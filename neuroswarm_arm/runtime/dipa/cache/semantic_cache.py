"""Lightweight semantic / MinHash prompt dedup for prefix cache."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


def _shingles(text: str, width: int = 5) -> set[str]:
    tokens = re.findall(r"\w+", text.lower())
    if len(tokens) < width:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + width]) for i in range(len(tokens) - width + 1)}


def _minhash_signature(shingles: set[str], *, bands: int = 8) -> tuple[int, ...]:
    if not shingles:
        return tuple(0 for _ in range(bands))
    sig: list[int] = []
    for band in range(bands):
        best = 2**63 - 1
        for shingle in shingles:
            digest = hashlib.sha256(f"{band}:{shingle}".encode()).digest()
            value = int.from_bytes(digest[:8], "big", signed=False)
            best = min(best, value)
        sig.append(best)
    return tuple(sig)


def jaccard_estimate(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / len(a)


@dataclass
class SemanticCacheEntry:
    key: str
    kv_id: str
    signature: tuple[int, ...]


@dataclass
class SemanticCache:
    """Exact hash + MinHash band lookup for prompt prefixes."""

    threshold: float = 0.75
    _exact: dict[str, str] = field(default_factory=dict)
    _entries: list[SemanticCacheEntry] = field(default_factory=list)
    hits: int = 0
    misses: int = 0

    def _hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8", errors="ignore")).hexdigest()[:24]

    def store(self, prompt: str, kv_id: str) -> str:
        key = self._hash(prompt)
        self._exact[key] = kv_id
        sig = _minhash_signature(_shingles(prompt))
        self._entries.append(SemanticCacheEntry(key=key, kv_id=kv_id, signature=sig))
        return key

    def lookup(self, prompt: str) -> str | None:
        key = self._hash(prompt)
        if key in self._exact:
            self.hits += 1
            return self._exact[key]
        sig = _minhash_signature(_shingles(prompt))
        best_id: str | None = None
        best_score = 0.0
        for entry in self._entries:
            score = jaccard_estimate(sig, entry.signature)
            if score > best_score:
                best_score = score
                best_id = entry.kv_id
        if best_id is not None and best_score >= self.threshold:
            self.hits += 1
            return best_id
        self.misses += 1
        return None

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0
