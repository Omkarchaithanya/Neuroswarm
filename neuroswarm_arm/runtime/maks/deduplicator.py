"""Deduplicator — alias / extend DeduplicationEngine for Memory OS naming."""

from __future__ import annotations

from .dedup import DedupEntry, DeduplicationEngine, DedupStats

# Memory OS name
Deduplicator = DeduplicationEngine

__all__ = ["Deduplicator", "DeduplicationEngine", "DedupEntry", "DedupStats"]
