"""Early-accept vs escalate on the quality-cascade path."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.confidence.engine import (
    quality_path_accept_threshold,
    should_early_accept_quality,
    text_quality_score,
)
from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config
from neuroswarm_arm.runtime.armcascade.metrics.prometheus import ASCRMetrics


def test_short_clear_answer_scores_above_quality_threshold() -> None:
    cfg = load_ascr_config()
    text = "Arm Neoverse V2 is the CPU architecture used by GCP Axion C4A."
    score = text_quality_score(text, cfg.get("confidence"))
    thresh = quality_path_accept_threshold(cfg)
    assert score >= thresh, (score, thresh)
    assert should_early_accept_quality(
        score, tier_id=1, threshold=thresh, cfg=cfg
    )


def test_uncertain_answer_does_not_early_accept() -> None:
    cfg = load_ascr_config()
    text = "I don't know what that means and cannot answer."
    score = text_quality_score(text, cfg.get("confidence"))
    thresh = quality_path_accept_threshold(cfg)
    assert score < thresh
    assert not should_early_accept_quality(
        score, tier_id=1, threshold=thresh, cfg=cfg
    )


def test_empty_text_never_accepts() -> None:
    cfg = load_ascr_config()
    score = text_quality_score("", cfg.get("confidence"))
    assert score == 0.0
    assert not should_early_accept_quality(
        score, tier_id=1, threshold=0.55, cfg=cfg
    )


def test_tier3_forced_accept_via_engine_rule() -> None:
    """Tier 3 is terminal; early-accept helper may still be false below floor."""
    assert should_early_accept_quality(0.9, tier_id=3, threshold=0.55, cfg={})
    # Below floor on tier3: helper returns False — engine uses `or tier_id >= 3`.
    assert not should_early_accept_quality(0.1, tier_id=3, threshold=0.55, cfg={})


def test_speculation_gain_zero_in_quality_mode() -> None:
    m = ASCRMetrics()
    m.record_round(
        accepted_tokens=32,
        rejected_tokens=0,
        draft_tokens=32,
        latency_ms=100.0,
        tier_used=1,
        mode="quality_cascade",
        logits_available=False,
    )
    assert m.snapshot().get("ascr_speculation_gain", -1) == 0.0


def test_speculation_gain_nonzero_in_speculative_mode() -> None:
    m = ASCRMetrics()
    m.record_round(
        accepted_tokens=8,
        rejected_tokens=0,
        draft_tokens=8,
        latency_ms=50.0,
        tier_used=1,
        mode="speculative",
        logits_available=True,
    )
    assert m.snapshot().get("ascr_speculation_gain", 0.0) == 1.0


def test_quality_thresholds_loaded_from_yaml() -> None:
    cfg = load_ascr_config()
    d = cfg.get("defaults") or {}
    assert float(d.get("quality_accept_threshold", 0)) == 0.55
    assert float(d.get("quality_early_accept_floor", 0)) == 0.52
