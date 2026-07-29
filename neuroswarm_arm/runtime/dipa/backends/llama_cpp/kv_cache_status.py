"""Live llama-server per-slot KV cache introspection (tiers 1/2/3)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from .slot_client import SlotClient
except ImportError:  # standalone script import via importlib
    from slot_client import SlotClient  # type: ignore[no-redef]

TIER_LABELS = {
    1: "tier1",
    2: "tier2",
    3: "tier3",
}

TIER_MODELS = {
    1: os.getenv("NSA_MODEL_TIER1", "Qwen2.5-0.5B-Instruct-Q4_0"),
    2: os.getenv("NSA_MODEL_TIER2", "Qwen2.5-3B-Instruct-Q4_0"),
    3: os.getenv("NSA_MODEL_TIER3", "DeepSeek-R1-Distill-Qwen-7B-Q4_0"),
}


def tier_urls_from_env() -> dict[int, str]:
    return {
        1: os.getenv("NSA_TIER1_URL", "http://127.0.0.1:8081").rstrip("/"),
        2: os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8082").rstrip("/"),
        3: os.getenv("NSA_TIER3_URL", "http://127.0.0.1:8083").rstrip("/"),
    }


@dataclass(slots=True)
class SlotKvStatus:
    id: int
    n_ctx: int
    kv_tokens: int
    prompt_tokens_cache: int | None = None
    prompt_tokens_processed: int | None = None
    prompt_tokens_total: int | None = None
    n_decoded: int = 0
    utilization_pct: float = 0.0
    is_processing: bool = False
    state: str = "empty"


@dataclass(slots=True)
class TierKvCacheStatus:
    tier: int
    label: str
    url: str
    model: str
    healthy: bool
    total_slots: int
    n_ctx_per_slot: int
    slots_endpoint: bool
    metrics_endpoint: bool
    slots: list[SlotKvStatus] = field(default_factory=list)
    total_kv_tokens: int = 0
    total_kv_capacity: int = 0
    utilization_pct: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_int(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return None


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    """Append NDJSON debug line when NSA_KV_CACHE_DEBUG=1."""
    if os.getenv("NSA_KV_CACHE_DEBUG", "").strip() not in {"1", "true", "yes"}:
        return
    # #region agent log
    try:
        root = Path(__file__).resolve().parents[5]
        log_path = root / "debug-e496d4.log"
        payload = {
            "sessionId": "e496d4",
            "runId": os.getenv("NSA_KV_CACHE_DEBUG_RUN", "pre-fix"),
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # #endregion


def _parse_prometheus(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    if not text:
        return out
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        try:
            out[name] = float(parts[-1])
        except ValueError:
            continue
    return out


def _slot_state(
    *,
    kv_tokens: int,
    is_processing: bool,
    has_task: bool,
) -> str:
    if is_processing:
        return "processing"
    if kv_tokens > 0:
        return "cached"
    if has_task:
        return "idle"
    return "empty"


def _estimate_slot_kv_tokens(
    slot: dict[str, Any],
    *,
    tokenize: Any | None = None,
    is_processing: bool = False,
) -> tuple[int, int | None, int | None, int | None, int, str]:
    """Return (kv_tokens, cache, processed, n_prompt_tokens, n_decoded, method)."""
    next_token = slot.get("next_token") if isinstance(slot.get("next_token"), dict) else {}
    n_decoded = _first_int(next_token, "n_decoded") or 0

    cache = _first_int(
        slot,
        "n_prompt_tokens_cache",
        "prompt_tokens_cache",
        "cache_n",
    )
    processed = _first_int(
        slot,
        "n_prompt_tokens_processed",
        "prompt_tokens_processed",
        "prompt_n",
    )
    n_prompt = _first_int(
        slot,
        "n_prompt_tokens",
        "n_token_total",
        "n_tokens",
        "n_tokens_cached",
    )

    generated = slot.get("generated")
    generated_n = 0
    if (
        not is_processing
        and n_decoded == 0
        and isinstance(generated, str)
        and generated.strip()
        and tokenize is not None
    ):
        try:
            generated_n = len(tokenize(generated))
        except Exception:
            generated_n = 0

    # Active prefill/decode: llama-server exposes incremental counters.
    if is_processing and cache is not None and processed is not None:
        kv = cache + processed + n_decoded
        return kv, cache, processed, n_prompt, n_decoded, "processing_cache_processed_decoded"

    # Idle or post-generation: n_prompt_tokens is input prompt size; completions
    # live in next_token.n_decoded while streaming, or in `generated` after idle.
    if n_prompt is not None:
        completion = n_decoded if n_decoded > 0 else generated_n
        kv = n_prompt + completion
        method = "prompt_plus_decoded" if n_decoded > 0 else "prompt_plus_generated"
        return kv, cache, processed, n_prompt, n_decoded, method

    prompt_text = slot.get("prompt")
    if isinstance(prompt_text, str) and prompt_text.strip() and tokenize is not None:
        try:
            tokens = tokenize(prompt_text)
            if tokens:
                kv = len(tokens) + (n_decoded if n_decoded > 0 else generated_n)
                return (
                    kv,
                    cache,
                    processed,
                    len(tokens),
                    n_decoded,
                    "tokenized_prompt_plus_completion",
                )
        except Exception:
            pass

    if cache is not None and processed is not None:
        kv = cache + processed + n_decoded
        return kv, cache, processed, n_prompt, n_decoded, "fallback_cache_processed_decoded"

    return n_decoded, cache, processed, n_prompt, n_decoded, "decoded_only"


def _normalize_slots(
    raw_slots: list[dict[str, Any]],
    *,
    default_n_ctx: int,
    total_slots: int,
    tokenize: Any | None = None,
) -> list[SlotKvStatus]:
    by_id: dict[int, dict[str, Any]] = {}
    for item in raw_slots:
        if not isinstance(item, dict):
            continue
        slot_id = _first_int(item, "id", "id_slot")
        if slot_id is None:
            continue
        by_id[int(slot_id)] = item

    normalized: list[SlotKvStatus] = []
    for slot_id in range(max(total_slots, len(by_id))):
        raw = by_id.get(slot_id, {"id": slot_id})
        n_ctx = _first_int(raw, "n_ctx") or default_n_ctx
        is_processing = bool(raw.get("is_processing"))
        has_task = bool(raw.get("id_task") or raw.get("params"))

        kv_tokens, cache, processed, total_prompt, n_decoded, method = _estimate_slot_kv_tokens(
            raw,
            tokenize=tokenize,
            is_processing=is_processing,
        )
        # #region agent log
        _debug_log(
            "A",
            "kv_cache_status._normalize_slots",
            "slot_kv_estimate",
            {
                "slot_id": slot_id,
                "is_processing": is_processing,
                "method": method,
                "kv_tokens": kv_tokens,
                "cache": cache,
                "processed": processed,
                "n_prompt_tokens": total_prompt,
                "n_decoded": n_decoded,
                "has_generated": bool(raw.get("generated")),
                "raw_keys": sorted(raw.keys()),
            },
        )
        # #endregion
        util = (kv_tokens / n_ctx * 100.0) if n_ctx > 0 else 0.0
        normalized.append(
            SlotKvStatus(
                id=slot_id,
                n_ctx=n_ctx,
                kv_tokens=kv_tokens,
                prompt_tokens_cache=cache,
                prompt_tokens_processed=processed,
                prompt_tokens_total=total_prompt,
                n_decoded=n_decoded,
                utilization_pct=round(util, 2),
                is_processing=is_processing,
                state=_slot_state(
                    kv_tokens=kv_tokens,
                    is_processing=is_processing,
                    has_task=has_task,
                ),
            )
        )
    return normalized


def fetch_tier_kv_cache_status(
    tier: int,
    base_url: str | None = None,
    *,
    timeout_s: float = 10.0,
) -> TierKvCacheStatus:
    """Query one llama-server tier for live KV cache occupancy."""
    urls = tier_urls_from_env()
    url = (base_url or urls.get(tier) or "").rstrip("/")
    label = TIER_LABELS.get(tier, f"tier{tier}")
    model = TIER_MODELS.get(tier, "unknown")
    client = SlotClient(url, timeout_s=timeout_s)

    status = TierKvCacheStatus(
        tier=tier,
        label=label,
        url=url,
        model=model,
        healthy=False,
        total_slots=0,
        n_ctx_per_slot=0,
        slots_endpoint=False,
        metrics_endpoint=False,
    )

    try:
        health = client.health()
        status.healthy = bool(health.get("ok"))
        if not status.healthy:
            status.error = str(health.get("error") or health.get("body") or "unhealthy")
            return status
    except Exception as exc:  # noqa: BLE001
        status.error = str(exc)
        return status

    props: dict[str, Any] = {}
    try:
        props = client.props()
    except Exception:
        props = {}

    default_gen = props.get("default_generation_settings") if isinstance(props, dict) else {}
    if isinstance(default_gen, dict):
        status.n_ctx_per_slot = _first_int(default_gen, "n_ctx") or status.n_ctx_per_slot
        params = default_gen.get("params")
        if status.n_ctx_per_slot == 0 and isinstance(params, dict):
            status.n_ctx_per_slot = _first_int(params, "n_ctx") or 0

    status.total_slots = _first_int(props, "total_slots") or 0
    status.slots_endpoint = bool(props.get("endpoint_slots"))
    status.metrics_endpoint = bool(props.get("endpoint_metrics"))
    if isinstance(props.get("model_alias"), str):
        status.model = props["model_alias"]

    metrics_text = ""
    try:
        metrics_text = client.metrics_text()
        status.metrics = _parse_prometheus(metrics_text)
        status.metrics_endpoint = status.metrics_endpoint or bool(metrics_text.strip())
    except Exception:
        pass

    # llama.cpp exposes peak prompt length across slots via prometheus.
    peak = status.metrics.get("llamacpp:n_tokens_max")
    if peak is not None and status.n_ctx_per_slot == 0:
        status.n_ctx_per_slot = int(peak)

    tokenize = None
    try:
        tokenize = client.tokenize
    except Exception:
        tokenize = None

    raw_slots: list[dict[str, Any]] = []
    try:
        raw_slots = client.slots()
        status.slots_endpoint = status.slots_endpoint or bool(raw_slots)
    except Exception as exc:  # noqa: BLE001
        if not status.error:
            status.error = f"/slots: {exc}"

    if status.total_slots <= 0:
        status.total_slots = max(len(raw_slots), 1)

    if status.n_ctx_per_slot <= 0:
        for slot in raw_slots:
            n_ctx = _first_int(slot, "n_ctx")
            if n_ctx:
                status.n_ctx_per_slot = n_ctx
                break

    status.slots = _normalize_slots(
        raw_slots,
        default_n_ctx=status.n_ctx_per_slot or 4096,
        total_slots=status.total_slots,
        tokenize=tokenize,
    )
    # #region agent log
    peak = status.metrics.get("llamacpp:n_tokens_max")
    _debug_log(
        "E",
        "kv_cache_status.fetch_tier_kv_cache_status",
        "tier_slots_summary",
        {
            "tier": tier,
            "url": url,
            "slot_count": len(raw_slots),
            "n_tokens_max": peak,
            "sum_kv_tokens": sum(s.kv_tokens for s in status.slots),
            "raw_slots": raw_slots,
        },
    )
    # #endregion
    status.total_kv_tokens = sum(s.kv_tokens for s in status.slots)
    status.total_kv_capacity = sum(s.n_ctx for s in status.slots)
    if status.total_kv_capacity > 0:
        status.utilization_pct = round(
            status.total_kv_tokens / status.total_kv_capacity * 100.0, 2
        )

    if not status.slots_endpoint and not status.error:
        status.error = (
            "llama-server /slots not enabled — add --slots to tier command "
            "(see docker-compose.yaml)"
        )
    return status


def fetch_all_tier_kv_cache_status(
    tiers: list[int] | None = None,
    *,
    timeout_s: float = 10.0,
) -> list[TierKvCacheStatus]:
    selected = tiers or [1, 2, 3]
    urls = tier_urls_from_env()
    out: list[TierKvCacheStatus] = []
    for tier in selected:
        out.append(
            fetch_tier_kv_cache_status(
                tier,
                urls.get(tier),
                timeout_s=timeout_s,
            )
        )
    return out


def format_tier_table(statuses: list[TierKvCacheStatus]) -> str:
    lines: list[str] = []
    for st in statuses:
        health = "ok" if st.healthy else "DOWN"
        lines.append(
            f"TIER {st.tier} ({st.label})  {st.url}  model={st.model}  health={health}"
        )
        if st.error and not st.healthy:
            lines.append(f"  error: {st.error}")
            lines.append("")
            continue
        if st.error:
            lines.append(f"  warn: {st.error}")
        lines.append(
            f"  slots={st.total_slots} ctx_per_slot={st.n_ctx_per_slot} "
            f"total_kv={st.total_kv_tokens}/{st.total_kv_capacity} "
            f"({st.utilization_pct}% util)"
        )
        if st.metrics:
            peak = st.metrics.get("llamacpp:n_tokens_max")
            prompt_total = st.metrics.get("llamacpp:prompt_tokens_total")
            if peak is not None or prompt_total is not None:
                lines.append(
                    f"  metrics: n_tokens_max={peak} prompt_tokens_total={prompt_total}"
                )
        lines.append("  slot  kv_tokens  cached  processed  decoded  n_ctx  util%  state")
        for slot in st.slots:
            lines.append(
                f"  {slot.id:4d}  {slot.kv_tokens:9d}  "
                f"{_fmt_opt(slot.prompt_tokens_cache):7s}  "
                f"{_fmt_opt(slot.prompt_tokens_processed):9s}  "
                f"{slot.n_decoded:7d}  {slot.n_ctx:5d}  "
                f"{slot.utilization_pct:5.1f}  {slot.state}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fmt_opt(value: int | None) -> str:
    return "-" if value is None else str(value)
