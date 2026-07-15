"""Scoring engine tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import (
    DeterministicScorer,
    FallbackCandidate,
    default_policy,
)

from .conftest import make_catalog, make_plan, make_signals


def test_scoring_deterministic_order():
    scorer = DeterministicScorer()
    cands = [
        FallbackCandidate(
            candidate_id="a",
            model_id="Qwen3-3B",
            backend="llama_cpp",
            quant="Q4_K_M",
            quality_delta=-0.1,
        ),
        FallbackCandidate(
            candidate_id="b",
            model_id="Phi-4-Mini",
            backend="llama_cpp",
            quant="Q4_K_M",
            quality_delta=-0.2,
        ),
    ]
    r1 = scorer.rank(
        cands,
        plan=make_plan(),
        signals=make_signals(),
        policy=default_policy(),
        catalog=make_catalog(),
        health_score=0.5,
    )
    r2 = scorer.rank(
        cands,
        plan=make_plan(),
        signals=make_signals(),
        policy=default_policy(),
        catalog=make_catalog(),
        health_score=0.5,
    )
    assert [s.candidate.candidate_id for s in r1] == [
        s.candidate.candidate_id for s in r2
    ]
    assert all(0.0 <= s.score <= 1.0 for s in r1)


def test_score_factors_present():
    scorer = DeterministicScorer()
    ranked = scorer.rank(
        [
            FallbackCandidate(
                candidate_id="a",
                model_id="Gemma",
                backend="llama_cpp",
                quant="Q4_K_M",
            )
        ],
        plan=make_plan(),
        signals=make_signals(),
        policy=default_policy(),
        catalog=make_catalog(),
        health_score=0.8,
    )
    assert "quality" in ranked[0].factors
    assert "latency" in ranked[0].factors
    assert "budget_fit" in ranked[0].factors
