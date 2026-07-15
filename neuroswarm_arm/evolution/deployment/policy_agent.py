"""ASCR PolicyRegistry-backed RL agent — reads active AROP policy."""

from __future__ import annotations

from neuroswarm_arm.evolution.optimization.policy_registry import PolicyRegistry
from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import (
    HeuristicPolicyAgent,
    RLAction,
    RLObservation,
    RLPolicyAgent,
)


class PolicyRegistryBackedAgent(RLPolicyAgent):
    """Feeds ASCR from AROP PolicyRegistry without forking ASCR internals."""

    def __init__(
        self,
        registry: PolicyRegistry,
        *,
        fallback: RLPolicyAgent | None = None,
        agent_id: str = "default",
    ) -> None:
        self.registry = registry
        self.fallback = fallback or HeuristicPolicyAgent()
        self.agent_id = agent_id

    def act(self, obs: RLObservation) -> RLAction:
        policy = self.registry.resolve(agent_id=self.agent_id)
        if policy is None:
            return self.fallback.act(obs)
        p = policy.parameters
        return RLAction(
            draft_len=int(p.get("draft_len", 8)),
            accept_threshold=float(p.get("accept_threshold", 0.7)),
            verify_batch_size=int(p.get("verify_batch", 1)),
            escalate_threshold=float(p.get("escalate_threshold", 0.4)),
            speculation_depth=int(p.get("speculation_depth", 1)),
        )
