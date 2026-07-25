"""Dynamic threshold engine (RL-agent aware)."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ThresholdEngine
from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import (
    HeuristicPolicyAgent,
    RLObservation,
    RLPolicyAgent,
)
from neuroswarm_arm.runtime.armcascade.interfaces.types import ThresholdInputs, ThresholdSet


class AdaptiveThresholdEngine(ThresholdEngine):
    def __init__(self, agent: RLPolicyAgent | None = None) -> None:
        self.agent = agent or HeuristicPolicyAgent()

    def compute(self, inputs: ThresholdInputs) -> ThresholdSet:
        if isinstance(self.agent, HeuristicPolicyAgent):
            self.agent.base_draft_len = inputs.base_draft_len
            self.agent.base_accept = inputs.base_accept_threshold
            self.agent.base_escalate = inputs.base_escalate_threshold
            self.agent.base_batch = inputs.base_verify_batch
            self.agent.base_depth = inputs.base_depth

        obs = RLObservation(
            acceptance_history=inputs.historical_acceptance,
            cpu_utilization=inputs.cpu_utilization,
            kv_pressure=inputs.kv_pressure,
            latency_budget_ms=inputs.latency_budget_ms,
            latency_used_ms=inputs.latency_used_ms,
            task_complexity=inputs.complexity,
            entropy_estimate=inputs.entropy_estimate,
            numa_locality=inputs.numa_locality,
            reasoning_confidence=inputs.governor_cap,
        )
        action = self.agent.act(obs)
        max_rounds = max(1, int(getattr(inputs, "base_max_rounds", 4) or 4))
        return ThresholdSet(
            draft_len=max(1, int(action.draft_len)),
            accept_threshold=float(action.accept_threshold),
            verify_batch_size=max(1, int(action.verify_batch_size)),
            escalate_threshold=float(action.escalate_threshold),
            speculation_depth=max(1, int(action.speculation_depth)),
            max_rounds=max_rounds,
            quality_accept_threshold=min(
                0.95, max(0.35, float(action.accept_threshold) - 0.15)
            ),
            quality_early_accept_floor=min(
                0.9, max(0.3, float(action.accept_threshold) - 0.18)
            ),
        )
