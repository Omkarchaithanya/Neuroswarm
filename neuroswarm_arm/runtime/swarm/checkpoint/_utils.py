"""Internal helpers for Checkpoint Manager (no peer-subsystem imports)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "ckpt_") -> str:
    return f"{prefix}{uuid4().hex}"


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def estimate_size_bytes(payload: Any) -> int:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return len(raw.encode("utf-8"))
