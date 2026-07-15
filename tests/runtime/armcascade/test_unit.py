"""Unit tests — classifier, acceptance, thresholds, escalation, registries."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.acceptance.engine import AdaptiveAcceptanceEngine
from neuroswarm_arm.runtime.armcascade.classifier.heuristic import HeuristicRequestClassifier
from neuroswarm_arm.runtime.armcascade.config.loader import (
    load_ascr_config,
    parse_escalation_graphs,
)
from neuroswarm_arm.runtime.armcascade.escalation.engine import GraphEscalationEngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    AcceptanceAction,
    AcceptanceSignals,
    EscalationState,
    TaskKind,
    ThresholdInputs,
)
from neuroswarm_arm.runtime.armcascade.plugins import load_plugins
from neuroswarm_arm.runtime.armcascade.proposal.registry import (
    ProposalRegistry,
    VerifierRegistry,
    known_proposers,
    known_verifiers,
)
from neuroswarm_arm.runtime.armcascade.thresholds.engine import AdaptiveThresholdEngine
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest


def test_load_ascr_config() -> None:
    cfg = load_ascr_config()
    assert cfg.get("enabled") is True
    assert "defaults" in cfg
    assert cfg["defaults"]["proposal_strategy"] == "draft_model"


def test_plugin_registration() -> None:
    load_plugins()
    proposers = known_proposers()
    verifiers = known_verifiers()
    assert "draft_model" in proposers
    assert "self_speculation" in proposers
    assert "eagle" in proposers
    assert "block" in verifiers
    assert "tree" in verifiers
    reg = ProposalRegistry()
    assert reg.get("draft_model").name == "draft_model"
    vreg = VerifierRegistry()
    assert vreg.get("block").name == "block"


def test_classifier_code_and_tools() -> None:
    clf = HeuristicRequestClassifier()
    req = InferenceRequest(
        messages=[{"role": "user", "content": "fix this python def bug ```code```"}],
        tool_names=["github"],
    )
    c = clf.classify(req)
    assert c.task_kind in {TaskKind.CODE, TaskKind.TOOL_USE}
    assert c.recommended_strategy


def test_threshold_adapts_to_history() -> None:
    eng = AdaptiveThresholdEngine()
    low = eng.compute(
        ThresholdInputs(
            historical_acceptance=0.3,
            entropy_estimate=0.9,
            base_draft_len=8,
            latency_budget_ms=1000,
            latency_used_ms=100,
        )
    )
    high = eng.compute(
        ThresholdInputs(
            historical_acceptance=0.95,
            entropy_estimate=0.2,
            base_draft_len=8,
            latency_budget_ms=5000,
            latency_used_ms=100,
        )
    )
    assert low.draft_len <= high.draft_len


def test_acceptance_escalate_on_low_confidence() -> None:
    eng = AdaptiveAcceptanceEngine()
    decision = eng.decide(
        AcceptanceSignals(
            confidence=0.0,
            agreement=0.1,
            entropy=0.9,
            quality_score=0.1,
            historical_acceptance=0.5,
            task_kind=TaskKind.REASONING,
            tool_confidence=0.0,
            reasoning_confidence=0.2,
            latency_budget_ms=4000,
            latency_used_ms=100,
            cpu_utilization=0.5,
            kv_pressure=0.0,
            cache_hit_ratio=0.0,
            draft_len=8,
            accepted_prefix_len=0,
            accept_threshold=0.7,
            escalate_threshold=0.4,
        )
    )
    assert decision.action in {
        AcceptanceAction.ESCALATE,
        AcceptanceAction.REJECT,
    }


def test_escalation_graph_linear() -> None:
    graphs = parse_escalation_graphs(
        {
            "default_linear": {
                "start": "tier1",
                "nodes": {
                    "tier1": {"kind": "tier", "tier_id": 1},
                    "tier2": {"kind": "tier", "tier_id": 2},
                    "accept": {"kind": "accept"},
                },
                "edges": [
                    {"source": "tier1", "target": "accept", "condition": "high_confidence"},
                    {"source": "tier1", "target": "tier2", "condition": "low_confidence"},
                    {"source": "tier2", "target": "accept", "condition": "always"},
                ],
            }
        }
    )
    g = graphs["default_linear"]
    eng = GraphEscalationEngine()
    edge = eng.next(g, EscalationState(current="tier1", confidence=0.2))
    assert edge is not None
    assert edge.target == "tier2"
    edge2 = eng.next(g, EscalationState(current="tier1", confidence=0.9))
    assert edge2 is not None
    assert edge2.target == "accept"


def test_self_speculation_proposer() -> None:
    import asyncio

    load_plugins()
    from neuroswarm_arm.runtime.armcascade.interfaces.types import (
        ASCRInitContext,
        ProposalRequest,
    )
    from neuroswarm_arm.runtime.armcascade.proposal.self_speculation import (
        SelfSpeculationProposer,
    )

    async def _run() -> None:
        p = SelfSpeculationProposer(draft_min=4, draft_max=12)
        await p.initialize(ASCRInitContext(config={}))
        words = " ".join(f"w{i}" for i in range(30))
        prop = await p.propose(
            ProposalRequest(
                prompt_text=words,
                messages=[{"role": "user", "content": words}],
                draft_len=8,
                max_tokens=8,
            )
        )
        assert prop.draft_len == 8
        assert prop.text

    asyncio.run(_run())
