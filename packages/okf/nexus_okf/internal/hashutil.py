from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def file_hash(path: Path) -> str:
    return content_hash(path.read_bytes())
