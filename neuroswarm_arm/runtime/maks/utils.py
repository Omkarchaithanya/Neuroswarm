"""MAKS utility helpers."""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any


def new_kv_id(prefix: str = "kv") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def new_token() -> str:
    return secrets.token_urlsafe(24)


def monotonic_ms() -> float:
    return time.monotonic() * 1000.0


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def safe_len(data: bytes | None) -> int:
    return 0 if data is None else len(data)


def merge_dict(a: dict[str, Any], b: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(a)
    if b:
        out.update(b)
    return out
