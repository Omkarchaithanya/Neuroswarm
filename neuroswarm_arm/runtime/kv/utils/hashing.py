"""Hashing helpers for prefix cache and deduplication."""

from __future__ import annotations

import hashlib
import uuid


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prefix_block_hash(prefix_hash: str, block_tokens_or_payload: bytes | str) -> str:
    """Hash = H(prefix_hash || current_block_tokens_or_payload)."""
    h = hashlib.sha256()
    h.update(prefix_hash.encode("utf-8") if prefix_hash else b"")
    h.update(b"|")
    if isinstance(block_tokens_or_payload, str):
        h.update(block_tokens_or_payload.encode("utf-8"))
    else:
        h.update(block_tokens_or_payload)
    return h.hexdigest()


def stable_id(prefix: str = "blk") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
