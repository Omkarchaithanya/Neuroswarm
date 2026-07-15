"""MAKS metadata helpers."""

from __future__ import annotations

import time
from typing import Any

from .models import KVIdentity, KVMetadata


def build_metadata(
    *,
    payload: bytes,
    identity: KVIdentity | None = None,
    backend: str = "",
    compression: str = "none",
    content_hash: str = "",
    prefix_hash: str = "",
    prompt_hash: str = "",
    producer: str = "",
    token_count: int = 0,
    layer_count: int = 0,
    head_count: int = 0,
    creation_latency_ms: float = 0.0,
    prefill_source: str = "",
    extra: dict[str, Any] | None = None,
) -> KVMetadata:
    ident = identity or KVIdentity()
    return KVMetadata(
        token_count=token_count,
        layer_count=layer_count,
        head_count=head_count,
        kv_size=len(payload),
        backend=backend,
        compression=compression,
        content_hash=content_hash,
        prefix_hash=prefix_hash,
        prompt_hash=prompt_hash,
        identity_hash=ident.fingerprint(),
        creation_latency_ms=creation_latency_ms,
        prefill_source=prefill_source,
        producer=producer,
        consumers=[],
        extra=dict(extra or {}),
    )


def touch_access(meta: KVMetadata, *, hit: bool) -> KVMetadata:
    data = meta.model_dump()
    if hit:
        data["hit_count"] = int(data.get("hit_count", 0)) + 1
        data["reuse_count"] = int(data.get("reuse_count", 0)) + 1
    else:
        data["miss_count"] = int(data.get("miss_count", 0)) + 1
    return KVMetadata.model_validate(data)


def now_ts() -> float:
    return time.time()
