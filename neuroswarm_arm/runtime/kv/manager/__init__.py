"""KV block manager package exports."""

from __future__ import annotations

from .block_manager import AllocateRequest, KVBlockManager
from .dedup import DeduplicationEngine, DedupResult
from .prefix import PrefixCacheEngine, PrefixMatchResult

__all__ = [
    "AllocateRequest",
    "DedupResult",
    "DeduplicationEngine",
    "KVBlockManager",
    "PrefixCacheEngine",
    "PrefixMatchResult",
]
