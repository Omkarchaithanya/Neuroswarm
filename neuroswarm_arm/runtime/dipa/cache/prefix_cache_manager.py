"""PrefixCacheManager — encapsulate SGLang radix + MAKS + llama slot stats."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.cache.semantic_cache import SemanticCache
from neuroswarm_arm.runtime.dipa.interfaces.pd import IPrefixCache


class PrefixCacheManager(IPrefixCache):
    def __init__(
        self,
        *,
        sglang_backend: Any | None = None,
        maks: Any | None = None,
        metrics: Any | None = None,
        semantic: SemanticCache | None = None,
    ) -> None:
        self.sglang_backend = sglang_backend
        self.maks = maks
        self.metrics = metrics
        self.semantic = semantic or SemanticCache()
        self._hits = 0
        self._misses = 0
        self._hit_tokens = 0
        self._total_tokens = 0
        self._warmed: set[str] = set()
        self._semantic_hits = 0

    def lookup(self, prefix_key: str) -> Mapping[str, Any]:
        key = _hash(prefix_key)
        warmed = key in self._warmed
        semantic_kv = self.semantic.lookup(prefix_key)
        if semantic_kv:
            self._semantic_hits += 1
        return {
            "key": key,
            "warmed": warmed,
            "hit_ratio": self.hit_ratio,
            "semantic_kv_id": semantic_kv,
            "semantic_hit_ratio": self.semantic.hit_ratio,
        }

    def lookup_semantic(self, prompt: str) -> str | None:
        return self.semantic.lookup(prompt)

    def record_semantic_store(self, prompt: str, kv_id: str) -> str:
        return self.semantic.store(prompt, kv_id)

    def record_hit(self, prefix_key: str, hit_tokens: int, total_tokens: int) -> None:
        total = max(0, int(total_tokens))
        hit = max(0, min(int(hit_tokens), total)) if total else 0
        self._total_tokens += total
        self._hit_tokens += hit
        if hit > 0:
            self._hits += 1
        else:
            self._misses += 1
        if self.metrics is not None:
            record = getattr(self.metrics, "record_prefix", None)
            if callable(record):
                record(hit_tokens=hit, total_tokens=total, hit_ratio=self.hit_ratio)

    async def warm(
        self, prefix_text: str, *, backend: str = "", session_id: str = ""
    ) -> Mapping[str, Any]:
        key = _hash(prefix_text)
        self._warmed.add(key)
        detail: dict[str, Any] = {"key": key, "session_id": session_id, "backend": backend}
        # Capability gate — skip MAKS prefix path when backend lacks prefix_reuse
        can_prefix = True
        if self.maks is not None:
            supports = getattr(self.maks, "supports_prefix_reuse", None)
            if callable(supports):
                try:
                    can_prefix = bool(supports())
                except Exception:
                    can_prefix = True
            matrix = getattr(self.maks, "capability_matrix", None)
            if callable(matrix) and backend:
                try:
                    caps = matrix().get(backend) or matrix().get("opaque") or {}
                    if "supports_prefix_reuse" in caps:
                        can_prefix = bool(caps["supports_prefix_reuse"])
                except Exception:
                    pass
        # Prefer SGLang warm when available (encapsulates RadixAttention).
        sgl = self.sglang_backend
        if sgl is not None:
            warm_fn = getattr(sgl, "warmup_prefix", None) or getattr(sgl, "warmup", None)
            if callable(warm_fn):
                try:
                    out = warm_fn(prefix_text) if warm_fn is getattr(sgl, "warmup_prefix", None) else warm_fn()
                    detail["sglang"] = out if isinstance(out, Mapping) else {"ok": True}
                except Exception as exc:  # noqa: BLE001
                    detail["sglang_error"] = str(exc)
        if self.maks is not None and can_prefix:
            prefetch = getattr(self.maks, "prefetch", None)
            if callable(prefetch):
                try:
                    prefetch(session_id or key)
                    detail["maks"] = True
                except Exception as exc:  # noqa: BLE001
                    detail["maks_error"] = str(exc)
        elif self.maks is not None and not can_prefix:
            detail["maks_skipped"] = "prefix_reuse_unsupported"
        return detail

    @property
    def hit_ratio(self) -> float:
        denom = self._hits + self._misses
        return (self._hits / denom) if denom else 0.0

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "hits": float(self._hits),
            "misses": float(self._misses),
            "hit_tokens": float(self._hit_tokens),
            "total_tokens": float(self._total_tokens),
            "hit_ratio": float(self.hit_ratio),
            "warmed": float(len(self._warmed)),
            "semantic_hits": float(self._semantic_hits),
            "semantic_hit_ratio": float(self.semantic.hit_ratio),
        }


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:24]
