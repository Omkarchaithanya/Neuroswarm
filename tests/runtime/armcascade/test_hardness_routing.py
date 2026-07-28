"""Hardness routing — mapper, DecisionEngine, ASCREngine start tier."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from neuroswarm_arm.runtime.armcascade.classifier.hardness import (
    HardnessBand,
    HardnessTierMapper,
)
from neuroswarm_arm.runtime.armcascade.classifier.heuristic import HeuristicRequestClassifier
from neuroswarm_arm.runtime.armcascade.config.loader import parse_escalation_graphs
from neuroswarm_arm.runtime.armcascade.escalation.engine import resolve_cascade_start_node
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.router.decision_engine import DecisionEngine
from neuroswarm_arm.runtime.dipa.router.execution_planner import ExecutionPlanner
from neuroswarm_arm.runtime.dipa.router.policy_engine import PolicyEngine
from neuroswarm_arm.runtime.dipa.routing.backend_selector import BackendSelector
from neuroswarm_arm.runtime.dipa.routing.model_router import ModelRouter
from neuroswarm_arm.runtime.dipa.routing.speculation_router import SpeculationRouter


def _mapper() -> HardnessTierMapper:
    return HardnessTierMapper()


def test_mapper_basic_prompt() -> None:
    req = InferenceRequest(
        messages=[{"role": "user", "content": "What is 2+2? Answer in one word."}]
    )
    result = _mapper().classify(req)
    assert result.band is HardnessBand.BASIC
    assert result.start_tier == 1


def test_mapper_medium_prompt() -> None:
    req = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": "Explain in 2 sentences the difference between TCP and UDP.",
            }
        ]
    )
    result = _mapper().classify(req)
    assert result.band in {HardnessBand.MEDIUM, HardnessBand.BASIC}
    assert result.start_tier >= 1


def test_mapper_advanced_reasoning_prompt() -> None:
    req = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": (
                    "Solve step by step: A train leaves at 9am at 60 mph. "
                    "Another leaves 300 miles away at 10am at 80 mph toward it. "
                    "When do they meet?"
                ),
            }
        ]
    )
    result = _mapper().classify(req)
    assert result.band is HardnessBand.ADVANCED
    assert result.start_tier == 3


def test_mapper_code_prompt() -> None:
    req = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": "Fix this python bug ```def foo(): pass``` stacktrace included",
            }
        ]
    )
    result = _mapper().classify(req)
    assert result.start_tier >= 2


def test_mapper_explain_advanced_style_stays_fast_tier() -> None:
    req = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": "explain me about vLLM in an advanced way",
            }
        ]
    )
    result = _mapper().classify(req)
    assert result.band is HardnessBand.BASIC
    assert result.start_tier == 1


def test_mapper_length_bump() -> None:
    long_prompt = "word " * 300
    req = InferenceRequest(messages=[{"role": "user", "content": long_prompt}])
    result = _mapper().classify(req)
    assert result.start_tier >= 2


def test_heuristic_sets_recommended_start_tier() -> None:
    clf = HeuristicRequestClassifier()
    req = InferenceRequest(messages=[{"role": "user", "content": "What is the capital of France?"}])
    c = clf.classify(req)
    assert c.recommended_start_tier in {1, 2, 3}
    assert c.hardness_band in {"basic", "medium", "advanced"}


def _build_decision_engine(*, hardness_enabled: bool = True) -> DecisionEngine:
    cascade_cfg = {
        "hardness_routing": {
            "enabled": hardness_enabled,
            "bands": {
                "basic": {"max_complexity": 0.40, "tier": 1},
                "medium": {"max_complexity": 0.65, "tier": 2},
                "advanced": {"tier": 3},
            },
            "length_bump": {"medium_min_tokens": 256, "advanced_min_tokens": 512},
        }
    }
    config = SimpleNamespace(
        cascade=cascade_cfg,
        pd_mode="off",
        prefill_backend="sglang",
        decode_backend="llama_cpp",
        pd_min_prompt_tokens=64,
    )
    policy = PolicyEngine()
    registry = MagicMock()
    registry.list.return_value = []
    return DecisionEngine(
        policy,
        ModelRouter(),
        BackendSelector(registry),
        SpeculationRouter(cascade_cfg),
        ExecutionPlanner(policy),
        config=config,
    )


def test_decision_engine_hardness_start_tier() -> None:
    engine = _build_decision_engine(hardness_enabled=True)
    easy = InferenceRequest(messages=[{"role": "user", "content": "What is 2+2?"}])
    plan = engine.decide(easy)
    assert plan.use_cascade is True
    assert plan.cascade_start_tier == 1
    assert plan.metadata["hardness"]["band"] == "basic"

    hard = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": "Reason step by step and prove why sqrt(2) is irrational.",
            }
        ]
    )
    hard_plan = engine.decide(hard)
    assert hard_plan.cascade_start_tier == 3
    assert hard_plan.metadata["hardness"]["band"] == "advanced"


def test_decision_engine_hardness_disabled() -> None:
    engine = _build_decision_engine(hardness_enabled=False)
    req = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": "Reason step by step and prove why sqrt(2) is irrational.",
            }
        ]
    )
    plan = engine.decide(req)
    assert plan.cascade_start_tier == 1
    assert "hardness" not in plan.metadata


def test_ascr_resolve_start_node() -> None:
    graphs = parse_escalation_graphs(
        {
            "default_linear": {
                "start": "tier1",
                "nodes": {
                    "tier1": {"kind": "tier", "tier_id": 1},
                    "tier2": {"kind": "tier", "tier_id": 2},
                    "tier3": {"kind": "tier", "tier_id": 3},
                    "accept": {"kind": "accept"},
                },
                "edges": [],
            }
        }
    )
    graph = graphs["default_linear"]
    assert resolve_cascade_start_node(graph, 1) == "tier1"
    assert resolve_cascade_start_node(graph, 2) == "tier2"
    assert resolve_cascade_start_node(graph, 3) == "tier3"
    assert resolve_cascade_start_node(graph, 99) == "tier3"
