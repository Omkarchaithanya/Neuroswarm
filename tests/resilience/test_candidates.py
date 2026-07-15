"""Candidate generation tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import CandidateGenerator, default_policy

from .conftest import make_catalog, make_plan, make_signals


def test_generates_chain_models():
    gen = CandidateGenerator()
    cands = gen.generate(
        make_plan(),
        make_signals(),
        default_policy(),
        make_catalog(),
    )
    models = {c.model_id for c in cands}
    assert "Qwen3-3B" in models or "Phi-4-Mini" in models
    assert len(cands) >= 1


def test_candidates_are_deterministic():
    gen = CandidateGenerator()
    a = gen.generate(make_plan(), make_signals(), default_policy(), make_catalog())
    b = gen.generate(make_plan(), make_signals(), default_policy(), make_catalog())
    assert [c.model_id for c in a] == [c.model_id for c in b]
    assert [c.backend for c in a] == [c.backend for c in b]
    assert [c.quant for c in a] == [c.quant for c in b]
