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
        "is_processing": True,
    }
    kv, cache, processed, total, decoded, method = _estimate_slot_kv_tokens(
        slot, is_processing=True
    )
    assert kv == 375
    assert cache == 355
    assert processed == 8
    assert decoded == 12
    assert method == "processing_cache_processed_decoded"


def test_idle_slot_ignores_stale_processed_counter() -> None:
    """Idle slot with processed=1 must not report kv_tokens=1."""
    slot = {
        "id": 1,
        "n_ctx": 512,
        "n_prompt_tokens": 36,
        "n_prompt_tokens_cache": 0,
        "n_prompt_tokens_processed": 1,
        "next_token": {"n_decoded": 0},
        "generated": "x" * 200,
        "is_processing": False,
    }

    def _fake_tokenize(text: str) -> list[int]:
        return list(range(max(1, len(text) // 4)))

    kv, _, processed, n_prompt, decoded, method = _estimate_slot_kv_tokens(
        slot, tokenize=_fake_tokenize, is_processing=False
    )
    assert processed == 1
    assert n_prompt == 36
    assert decoded == 0
    assert kv > 36
    assert method == "prompt_plus_generated"


def test_next_token_list_parsing() -> None:
    slot = {
        "id": 0,
        "n_prompt_tokens": 60,
        "n_prompt_tokens_cache": 0,
        "n_prompt_tokens_processed": 1,
        "next_token": [{"n_decoded": 25, "n_remain": 39}],
        "is_processing": False,
    }
    kv, _, _, n_prompt, decoded, method = _estimate_slot_kv_tokens(slot, is_processing=False)
    assert decoded == 25
    assert n_prompt == 60
    assert kv == 85
    assert method == "prompt_plus_decoded_idle"


def test_apply_metrics_peak_caps_and_bumps() -> None:
    from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kv_cache_status import (
        SlotKvStatus,
        _apply_metrics_peak,
    )

    slots = [
        SlotKvStatus(id=0, n_ctx=512, kv_tokens=0, state="empty"),
        SlotKvStatus(
            id=1,
            n_ctx=512,
            kv_tokens=60,
            prompt_tokens_total=60,
            n_decoded=25,
            state="cached",
        ),
    ]
    _apply_metrics_peak(slots, 99.0)
    assert slots[1].kv_tokens == 85

    stale = [
        SlotKvStatus(
            id=0,
            n_ctx=2048,
            kv_tokens=95,
            prompt_tokens_total=40,
            n_decoded=55,
            state="cached",
        )
    ]
    _apply_metrics_peak(stale, 122.0)
    assert stale[0].kv_tokens == 95

    severe = [SlotKvStatus(id=0, n_ctx=512, kv_tokens=6, state="cached")]
    _apply_metrics_peak(severe, 151.0)
    assert severe[0].kv_tokens == 151


def test_processing_slot_prompt_plus_decoded() -> None:
    slot = {
        "id": 0,
        "n_prompt_tokens": 38,
        "n_prompt_tokens_cache": 0,
        "n_prompt_tokens_processed": 38,
        "next_token": {"n_decoded": 85},
        "is_processing": True,
    }
    kv, _, processed, _, decoded, method = _estimate_slot_kv_tokens(slot, is_processing=True)
    assert kv == 123
    assert processed == 38
    assert decoded == 85
    assert method == "processing_cache_processed_decoded"


def test_normalize_slots_fills_empty_slots() -> None:
    slots = _normalize_slots(
        [{"id": 0, "n_ctx": 1024, "n_prompt_tokens": 100, "n_prompt_tokens_processed": 5}],
        default_n_ctx=1024,
        total_slots=2,
    )
    assert len(slots) == 2
    assert slots[0].kv_tokens == 100
    assert slots[0].state == "cached"
    assert slots[1].kv_tokens == 0
    assert slots[1].state == "empty"
