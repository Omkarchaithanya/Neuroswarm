"""Deterministic rollback planning — no workflow / agent execution."""

from __future__ import annotations

from typing import Any, Mapping

from .events import EventBus
from .exceptions import RollbackPlanningError
from .metrics import RollbackMetrics
from .models import FailureObservation, RollbackLevel, RollbackStrategyKind
from .recovery import RollbackPlan
from .strategy import IRollbackStrategy, strategy_for


class RollbackPlanner:
    """Plan rollback from failure observation or recovery-plan mapping."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: RollbackMetrics | None = None,
        default_strategy: RollbackStrategyKind = RollbackStrategyKind.RESUME_CHECKPOINT,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or RollbackMetrics()
        self.default_strategy = default_strategy

    def plan(
        self,
        observation: FailureObservation | Mapping[str, Any],
        *,
        strategy: RollbackStrategyKind | IRollbackStrategy | str | None = None,
        level: RollbackLevel | str | None = None,
    ) -> RollbackPlan:
        obs = self._normalize(observation)
        strat_obj = self._resolve_strategy(strategy, obs)
        fields: dict[str, Any] = {
            "workflow_id": obs.workflow_id,
            "execution_id": obs.execution_id,
            "checkpoint_reference": obs.checkpoint_reference,
            "recovery_plan_reference": obs.recovery_plan_reference,
            "target_node": obs.node_id,
            "target_subgraph": obs.subgraph_id,
            "target_context": obs.context_id,
            "target_budget": obs.budget_envelope_id,
            "target_nodes": list(obs.failed_nodes),
            "reason": obs.reason,
            "metadata": dict(obs.metadata),
        }
        shaped = strat_obj.apply_plan(fields)
        if level is not None:
            shaped["level"] = (
                RollbackLevel(level) if isinstance(level, str) else level
            )
        else:
            shaped["level"] = shaped.get("rollback_level", RollbackLevel.WORKFLOW)

        strategy_kind = shaped.get("rollback_strategy", self.default_strategy)
        if isinstance(strategy_kind, str):
            strategy_kind = RollbackStrategyKind(strategy_kind)

        if (
            strategy_kind == RollbackStrategyKind.RESUME_CHECKPOINT
            and not shaped.get("checkpoint_reference")
            and not shaped.get("target_nodes")
            and not shaped.get("target_node")
        ):
            # Fall back to restart when nothing to resume
            strategy_kind = RollbackStrategyKind.RESTART_WORKFLOW
            shaped = strategy_for(strategy_kind).apply_plan(shaped)

        recovery_order = self._recovery_order(shaped, strategy_kind)
        deps = self._dependencies(recovery_order)

        if not shaped.get("workflow_id") or not shaped.get("execution_id"):
            raise RollbackPlanningError("workflow_id and execution_id required")

        plan = RollbackPlan(
            workflow_id=str(shaped["workflow_id"]),
            execution_id=str(shaped["execution_id"]),
            strategy=strategy_kind,
            level=shaped.get("level", RollbackLevel.WORKFLOW),
            checkpoint_reference=shaped.get("checkpoint_reference"),
            recovery_plan_reference=shaped.get("recovery_plan_reference"),
            target_node=shaped.get("target_node"),
            target_subgraph=shaped.get("target_subgraph"),
            target_context=shaped.get("target_context"),
            target_budget=shaped.get("target_budget"),
            target_nodes=list(shaped.get("target_nodes") or []),
            reason=str(shaped.get("reason") or ""),
            recovery_order=recovery_order,
            recovery_dependencies=deps,
            metadata=dict(shaped.get("metadata") or {}),
        )
        self.metrics.incr("rollback_count")
        self.metrics.record_strategy(strategy_kind.value)
        return plan

    def _normalize(
        self, observation: FailureObservation | Mapping[str, Any]
    ) -> FailureObservation:
        if isinstance(observation, FailureObservation):
            return observation
        data = dict(observation)
        # Accept RecoveryPlan-like mappings from Checkpoint Manager
        if "plan_id" in data and "recovery_plan_reference" not in data:
            data["recovery_plan_reference"] = data.pop("plan_id")
        else:
            data.pop("plan_id", None)
        if "checkpoint_id" in data and "checkpoint_reference" not in data:
            data["checkpoint_reference"] = data.pop("checkpoint_id")
        else:
            data.pop("checkpoint_id", None)
        if "resume_node_id" in data and "node_id" not in data:
            data["node_id"] = data.pop("resume_node_id")
        else:
            data.pop("resume_node_id", None)
        if "resume_subgraph_id" in data and "subgraph_id" not in data:
            data["subgraph_id"] = data.pop("resume_subgraph_id")
        else:
            data.pop("resume_subgraph_id", None)
        if "target_nodes" in data and "failed_nodes" not in data:
            data["failed_nodes"] = list(data.pop("target_nodes") or [])
        else:
            data.pop("target_nodes", None)
        allowed = set(FailureObservation.model_fields)
        data = {k: v for k, v in data.items() if k in allowed}
        return FailureObservation.model_validate(data)

    def _resolve_strategy(
        self,
        strategy: RollbackStrategyKind | IRollbackStrategy | str | None,
        obs: FailureObservation,
    ) -> Any:
        if strategy is None:
            if obs.node_id:
                return strategy_for(RollbackStrategyKind.RESTART_NODE)
            if obs.subgraph_id:
                return strategy_for(RollbackStrategyKind.RESTART_SUBGRAPH)
            if obs.context_id and not obs.checkpoint_reference:
                return strategy_for(RollbackStrategyKind.ROLLBACK_CONTEXT)
            if obs.budget_envelope_id and not obs.checkpoint_reference:
                return strategy_for(RollbackStrategyKind.ROLLBACK_BUDGET)
            if obs.checkpoint_reference:
                return strategy_for(self.default_strategy)
            return strategy_for(RollbackStrategyKind.RESTART_WORKFLOW)
        if isinstance(strategy, str):
            return strategy_for(strategy)
        if isinstance(strategy, RollbackStrategyKind):
            return strategy_for(strategy)
        return strategy

    def _recovery_order(
        self, fields: Mapping[str, Any], strategy: RollbackStrategyKind
    ) -> list[str]:
        order: list[str] = []
        if strategy in {
            RollbackStrategyKind.ROLLBACK_BUDGET,
            RollbackStrategyKind.RESUME_CHECKPOINT,
            RollbackStrategyKind.RESTART_WORKFLOW,
        }:
            if fields.get("target_budget"):
                order.append(f"budget:{fields['target_budget']}")
        if strategy in {
            RollbackStrategyKind.ROLLBACK_CONTEXT,
            RollbackStrategyKind.RESUME_CHECKPOINT,
            RollbackStrategyKind.RESTART_WORKFLOW,
        }:
            if fields.get("target_context"):
                order.append(f"context:{fields['target_context']}")
        if strategy == RollbackStrategyKind.ROLLBACK_METADATA:
            order.append(f"metadata:{fields.get('execution_id')}")
        if fields.get("target_subgraph"):
            order.append(f"subgraph:{fields['target_subgraph']}")
        nodes = list(fields.get("target_nodes") or [])
        if fields.get("target_node") and fields["target_node"] not in nodes:
            nodes.insert(0, fields["target_node"])
        for node in nodes:
            order.append(f"node:{node}")
        if fields.get("checkpoint_reference"):
            order.append(f"checkpoint:{fields['checkpoint_reference']}")
        if not order:
            order.append(f"workflow:{fields.get('workflow_id')}")
        return order

    def _dependencies(self, order: list[str]) -> dict[str, list[str]]:
        deps: dict[str, list[str]] = {}
        for i, step in enumerate(order):
            deps[step] = list(order[:i])
        return deps
