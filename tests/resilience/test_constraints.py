"""Constraint solver tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.resilience import (
    ConstraintSolver,
    ConstraintViolation,
    FallbackCandidate,
    default_policy,
)

from .conftest import make_catalog, make_plan, make_signals


def _cand(**kwargs) -> FallbackCandidate:
    data = {
        "candidate_id": "cand_1",
        "model_id": "Qwen3-3B",
        "backend": "llama_cpp",
        "quant": "Q4_K_M",
        "context_length": 8192,
        "thread_count": 4,
        "reasoning_budget": 256,
        "tools_enabled": True,
    }
    data.update(kwargs)
    return FallbackCandidate(**data)


def test_valid_candidate_passes():
    solver = ConstraintSolver()
    assert solver.validate(
        _cand(),
        plan=make_plan(),
        signals=make_signals(),
        policy=default_policy(),
        catalog=make_catalog(),
    )


def test_reject_unsupported_backend():
    solver = ConstraintSolver()
    with pytest.raises(ConstraintViolation) as exc:
        solver.validate(
            _cand(backend="vllm"),
            plan=make_plan(),
            signals=make_signals(),
            policy=default_policy(),
            catalog=make_catalog(),
            raise_on_fail=True,
        )
    assert exc.value.constraint == "backend"


def test_reject_context_too_small():
    solver = ConstraintSolver()
    ok = solver.validate(
        _cand(model_id="TinyLlama", context_length=2048, quant="Q4_K_M"),
        plan=make_plan(),
        signals=make_signals(context_tokens_needed=4000),
        policy=default_policy(),
        catalog=make_catalog(),
        raise_on_fail=False,
    )
    assert ok is False


def test_reject_tools_disabled_when_required():
    solver = ConstraintSolver()
    ok = solver.validate(
        _cand(tools_enabled=False),
        plan=make_plan(),
        signals=make_signals(tools_required=True),
        policy=default_policy(),
        catalog=make_catalog(),
        raise_on_fail=False,
    )
    assert ok is False


def test_filter_drops_invalid():
    solver = ConstraintSolver()
    cands = [_cand(), _cand(candidate_id="bad", backend="nope")]
    filtered = solver.filter(
        cands,
        plan=make_plan(),
        signals=make_signals(),
        policy=default_policy(),
        catalog=make_catalog(),
    )
    assert len(filtered) == 1
    assert filtered[0].candidate_id == "cand_1"
