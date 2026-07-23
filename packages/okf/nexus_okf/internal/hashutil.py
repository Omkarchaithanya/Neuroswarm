from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def hash_block(block: bytes | str) -> str:
    """Stable short SHA-256 hash for OKF block affinity keys."""
    if isinstance(block, str):
        block = block.encode("utf-8")
    return hashlib.sha256(block).hexdigest()[:16]


def file_hash(path: Path) -> str:
    return content_hash(path.read_bytes())
