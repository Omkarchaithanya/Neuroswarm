"""Tests for llama-server KV cache status parsing."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kv_cache_status import (
    _estimate_slot_kv_tokens,
    _normalize_slots,
    _parse_prometheus,
)


def test_parse_prometheus_kv_metrics() -> None:
    text = """
# HELP llamacpp:n_tokens_max Largest observed n_tokens.
# TYPE llamacpp:n_tokens_max counter
llamacpp:n_tokens_max 394.0
llamacpp:prompt_tokens_total 593
"""
    metrics = _parse_prometheus(text)
    assert metrics["llamacpp:n_tokens_max"] == 394.0
    assert metrics["llamacpp:prompt_tokens_total"] == 593.0


def test_estimate_slot_kv_tokens_from_cache_fields() -> None:
    slot = {
        "id": 0,
        "n_ctx": 4096,
        "n_prompt_tokens_cache": 355,
        "n_prompt_tokens_processed": 8,
        "next_token": {"n_decoded": 12},
    }
    kv, cache, processed, total, decoded = _estimate_slot_kv_tokens(slot)
    assert kv == 375
    assert cache == 355
    assert processed == 8
    assert decoded == 12


def test_normalize_slots_fills_empty_slots() -> None:
    slots = _normalize_slots(
        [{"id": 0, "n_ctx": 1024, "n_prompt_tokens_cache": 100, "n_prompt_tokens_processed": 5}],
        default_n_ctx=1024,
        total_slots=2,
    )
    assert len(slots) == 2
    assert slots[0].kv_tokens == 105
    assert slots[0].state == "cached"
    assert slots[1].kv_tokens == 0
    assert slots[1].state == "empty"
