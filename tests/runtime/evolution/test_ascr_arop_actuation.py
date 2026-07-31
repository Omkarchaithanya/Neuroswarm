"""ASCR AROP actuation — apply_rl_action reaches live thresholds (not PPO)."""

from __future__ import annotations

import pytest

from neuroswarm_arm.evolution.deployment.adapters import ASCRDeploymentAdapter
from neuroswarm_arm.evolution.rl.experience_store import OfflineRLTrainer
from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import (
    RLAction,
    RLObservation,
    StaticPolicyAgent,
)
from neuroswarm_arm.runtime.armcascade.interfaces.types import ThresholdInputs
from neuroswarm_arm.runtime.armcascade.thresholds.engine import AdaptiveThresholdEngine


class _FakeASCR:
    """Minimal stand-in when full ASCREngine needs heavy wiring."""

    def __init__(self) -> None:
        self.thresholds = AdaptiveThresholdEngine()
        self._arop_rl_action = None

    def apply_rl_action(self, action: RLAction) -> None:
        self.thresholds.agent = StaticPolicyAgent(action)
        self._arop_rl_action = action


def test_static_policy_agent_returns_fixed_action():
    action = RLAction(draft_len=3, accept_threshold=0.9, escalate_threshold=0.55)
    agent = StaticPolicyAgent(action)
    out = agent.act(RLObservation())
    assert out.draft_len == 3
    assert out.accept_threshold == 0.9
    assert out.escalate_threshold == 0.55


def test_adapter_apply_rl_action_changes_thresholds():
    target = _FakeASCR()
    adapter = ASCRDeploymentAdapter(target=target, dry_run=False)
    applied = adapter.apply(
        {
            "draft_len": 4,
            "accept_threshold": 0.85,
            "escalate_threshold": 0.5,
            "verify_batch": 2,
            "speculation_depth": 1,
        }
    )
    assert applied["draft_len"] == 4
    assert isinstance(target.thresholds.agent, StaticPolicyAgent)
    thr = target.thresholds.compute(
        ThresholdInputs(
            base_draft_len=8,
            base_accept_threshold=0.7,
            base_escalate_threshold=0.4,
            base_verify_batch=1,
            base_depth=1,
            historical_acceptance=0.5,
            cpu_utilization=0.5,
            kv_pressure=0.0,
            latency_budget_ms=4000.0,
            latency_used_ms=100.0,
            complexity=0.5,
            entropy_estimate=0.5,
            numa_locality=1.0,
            governor_cap=0.5,
        )
    )
    assert thr.draft_len == 4
    assert thr.accept_threshold == 0.85


def test_real_ascr_engine_apply_rl_action():
    from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
    from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config

    eng = ASCREngine(config=load_ascr_config(), registry=None, graphs={})
    eng.apply_rl_action(
        RLAction(draft_len=5, accept_threshold=0.8, escalate_threshold=0.45)
    )
    assert isinstance(eng.thresholds.agent, StaticPolicyAgent)
    thr = eng.thresholds.compute(
        ThresholdInputs(
            historical_acceptance=0.9,
            cpu_utilization=0.2,
            entropy_estimate=0.2,
            complexity=0.2,
        )
    )
    # Static agent ignores heuristic bumps from high accept_history
    assert thr.draft_len == 5
    assert thr.accept_threshold == 0.8


def test_offline_rl_trainer_refuses_ppo_and_grpo():
    trainer = OfflineRLTrainer()
    with pytest.raises(NotImplementedError, match="ADR 0005"):
        trainer.train_ppo()
    with pytest.raises(NotImplementedError, match="GRPO"):
        trainer.train_grpo()
