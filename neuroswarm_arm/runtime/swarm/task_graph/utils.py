"""Small helpers for the Task Graph subsystem."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    hid = uuid4().hex
    return f"{prefix}{hid}" if prefix else hid


def stable_hash(payload: Any) -> str:
    """Deterministic SHA-256 over a JSON-normalized payload."""
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, Mapping):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_unique(ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for i in ids:
        if i in seen:
            dupes.append(i)
        seen.add(i)
    return dupes


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
