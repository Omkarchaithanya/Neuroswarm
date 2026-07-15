"""Official-aligned GEPA subsystem tests (no gepa PyPI package required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from neuroswarm_arm.evolution.reflection.gepa import (
    ASIBuilder,
    ApprovalGate,
    CandidatePool,
    GEPAFacade,
    ParetoFront,
    TextArtifactDeployer,
    TextCandidate,
)
from neuroswarm_arm.evolution.reflection.gepa.candidate.models import FORBIDDEN_KEYS, validate_text_components


def test_asi_builder_aggregates_sources() -> None:
    builder = ASIBuilder()
    asi = builder.build(
        observations=[
            {"source": "performix", "metrics": {"latency_ms": 1200, "energy_joules": 3.0}},
            {"source": "cascade", "metrics": {"ascr_accept_rate": 0.55, "ascr_latency_ms": 900}},
        ],
        metrics={"cost_usd": 0.01, "kv_pressure": 0.4},
        profiling_asi=[
            {
                "profile_id": "p1",
                "backend": "llama",
                "quantization": "Q5",
                "observation": {"cpu_percent": 40.0, "ipc": 1.2},
                "recommendations": ["prefer cooler backend"],
            }
        ],
        mem0_snippets=["prior lesson: shorten system prompt"],
    )
    assert "performix" in asi.sources or "cascade" in asi.sources
    assert asi.records
    assert "latency" in asi.feedback_text().lower() or "Latency" in asi.feedback_text()


def test_text_candidate_rejects_hardware_keys() -> None:
    with pytest.raises(ValueError, match="forbids"):
        validate_text_components({"thread_count": "8"})
    for key in ("numa_placement", "accept_threshold", "draft_len"):
        assert key in FORBIDDEN_KEYS


def test_candidate_pool_no_overwrite() -> None:
    root = Path("work/arop_test_gepa_pool")
    root.mkdir(parents=True, exist_ok=True)
    pool = CandidatePool(store_path=root / "pool.json")
    a = TextCandidate.create({"system_prompt": "A"}, version="v0", candidate_id="same")
    pool.add(a)
    b = TextCandidate.create({"system_prompt": "B"}, version="v1", candidate_id="same")
    with pytest.raises(ValueError, match="overwrite"):
        pool.add(b)


def test_pareto_keeps_multiple_non_dominated() -> None:
    front = ParetoFront(objectives=("accuracy", "latency"))
    c1 = TextCandidate.create({"system_prompt": "fast"}, scores={"accuracy": 0.6, "latency": 100})
    c2 = TextCandidate.create({"system_prompt": "accurate"}, scores={"accuracy": 0.9, "latency": 500})
    c3 = TextCandidate.create({"system_prompt": "dominated"}, scores={"accuracy": 0.5, "latency": 600})
    members = front.update([c1, c2, c3])
    ids = {m.id for m in members}
    assert c1.id in ids
    assert c2.id in ids
    assert c3.id not in ids
    assert len(members) >= 2


def test_gepa_facade_local_loop() -> None:
    facade = GEPAFacade(work_dir=Path("work/arop_test_gepa_loop"))
    result = facade.run_local_loop(
        {"system_prompt": "You are helpful.", "routing_policy": "# route carefully\n"},
        trainset=[
            {"id": "a", "input": "q1", "expected": "a1"},
            {"id": "b", "input": "q2", "expected": "a2"},
        ],
        max_iterations=2,
        use_merge=True,
    )
    assert result.best is not None
    assert result.frontier
    assert isinstance(result.best.components["system_prompt"], str)
    selected = facade.pareto_select()
    assert selected is not None


def test_approval_required_for_text_deploy() -> None:
    root = Path("work/arop_test_gepa_deploy")
    root.mkdir(parents=True, exist_ok=True)
    okf = root / "okf"
    okf.mkdir(parents=True, exist_ok=True)
    gate = ApprovalGate()
    deployer = TextArtifactDeployer(okf_root=okf)
    cand = TextCandidate.create({"system_prompt": "deploy me"}, version="v1")
    denied = deployer.deploy(cand, require_approval=True, gate=gate)
    assert denied["success"] is False
    gate.submit(cand)
    gate.approve(cand.id, reviewer="test")
    approved = cand.mark_approved()
    ok = deployer.deploy(approved, require_approval=True, gate=gate)
    assert ok["success"] is True
    assert ok["paths"]
