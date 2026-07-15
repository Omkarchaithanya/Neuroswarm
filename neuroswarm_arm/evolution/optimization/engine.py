"""Optimization engine — materializes immutable RuntimePolicy candidates."""

from __future__ import annotations

import uuid
from typing import Any

from neuroswarm_arm.evolution.interfaces.optimization import PolicyOptimizer
from neuroswarm_arm.evolution.interfaces.reflection import PolicyDelta
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.policy import PolicyConstraints, RuntimePolicy
from neuroswarm_arm.evolution.optimization.knobs import clamp_parameters, layers_for_parameters
from neuroswarm_arm.evolution.optimization.policy_registry import PolicyRegistry


class OptimizationEngine(PolicyOptimizer):
    def __init__(
        self,
        registry: PolicyRegistry,
        *,
        constraints: PolicyConstraints | None = None,
        version_prefix: str = "v",
    ) -> None:
        self.registry = registry
        self.constraints = constraints or PolicyConstraints()
        self.version_prefix = version_prefix
        self._counter = 0

    def materialize(
        self,
        delta: PolicyDelta,
        *,
        parent: RuntimePolicy | None = None,
        version: str | None = None,
    ) -> CandidatePolicy:
        self._counter += 1
        base_params: dict[str, Any] = dict(parent.parameters) if parent else {}
        merged = clamp_parameters({**base_params, **dict(delta.parameters)})
        layers = delta.target_layers or layers_for_parameters(merged)
        if parent:
            layers = frozenset(set(layers) | set(parent.target_layers))
        ver = version or f"{self.version_prefix}{self._counter}"
        policy_id = f"pol_{uuid.uuid4().hex[:10]}"
        policy = RuntimePolicy.create(
            policy_id=policy_id,
            version=ver,
            parameters=merged,
            target_layers=layers,
            expected_reward=delta.expected_reward,
            confidence=delta.confidence,
            constraints=self.constraints,
            rollback_policy_id=parent.id if parent else None,
            parent_policy_id=parent.id if parent else None,
            explanation=delta.rationale,
        )
        self.registry.register(policy)
        return CandidatePolicy(
            candidate_id=f"cand_{uuid.uuid4().hex[:10]}",
            policy=policy,
            source=delta.source,
            metadata={"rationale": delta.rationale},
        )
