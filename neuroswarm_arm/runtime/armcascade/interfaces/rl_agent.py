"""RL-ready observation / action ports for future PPO agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class RLObservation:
    acceptance_history: float = 0.7
    cpu_utilization: float = 0.5
    kv_pressure: float = 0.0
    latency_budget_ms: float = 4000.0
    latency_used_ms: float = 0.0
    task_complexity: float = 0.5
    entropy_estimate: float = 0.5
    numa_locality: float = 1.0
    cache_hit_ratio: float = 0.0
    tool_confidence: float = 0.0
    reasoning_confidence: float = 0.5
    extras: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RLAction:
    draft_len: int = 8
    accept_threshold: float = 0.7
    verify_batch_size: int = 1
    escalate_threshold: float = 0.4
    speculation_depth: int = 1


class RLPolicyAgent(ABC):
    """Port for future PPO / bandit agents. Must not mutate ASCR internals."""

    @abstractmethod
    def act(self, obs: RLObservation) -> RLAction:
        raise NotImplementedError

    def observe_reward(self, reward: float) -> None:
        """Optional online update hook."""
        return None


class HeuristicPolicyAgent(RLPolicyAgent):
    """Deterministic heuristic stand-in until Performix/PPO wired."""

    def __init__(
        self,
        *,
        base_draft_len: int = 8,
        base_accept: float = 0.7,
        base_escalate: float = 0.4,
        base_batch: int = 1,
        base_depth: int = 1,
    ) -> None:
        self.base_draft_len = base_draft_len
        self.base_accept = base_accept
        self.base_escalate = base_escalate
        self.base_batch = base_batch
        self.base_depth = base_depth

    def act(self, obs: RLObservation) -> RLAction:
        draft = self.base_draft_len
        if obs.acceptance_history > 0.8 and obs.entropy_estimate < 0.4:
            draft = min(48, draft + 4)
        if obs.acceptance_history < 0.5 or obs.entropy_estimate > 0.7:
            draft = max(2, draft - 4)
        if obs.latency_used_ms > 0.7 * max(obs.latency_budget_ms, 1.0):
            draft = max(2, draft // 2)
        if obs.kv_pressure > 0.8:
            draft = max(2, draft - 2)

        accept = self.base_accept
        if obs.task_complexity > 0.7:
            accept = min(0.95, accept + 0.1)
        if obs.tool_confidence > 0.8:
            accept = max(0.4, accept - 0.05)

        escalate = self.base_escalate
        if obs.reasoning_confidence < 0.4:
            escalate = min(0.7, escalate + 0.1)

        batch = self.base_batch
        if obs.cpu_utilization < 0.4:
            batch = min(8, max(1, batch * 2))

        depth = self.base_depth
        if obs.acceptance_history > 0.75 and obs.cpu_utilization < 0.6:
            depth = min(3, depth + 1)

        return RLAction(
            draft_len=int(draft),
            accept_threshold=float(accept),
            verify_batch_size=int(batch),
            escalate_threshold=float(escalate),
            speculation_depth=int(depth),
        )
