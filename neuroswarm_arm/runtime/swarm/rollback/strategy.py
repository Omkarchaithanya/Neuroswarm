"""Pure rollback strategy objects — shape plans only, no I/O / execution."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from pydantic import Field

from .models import RollbackLevel, RollbackStrategyKind, _Frozen


@runtime_checkable
class IRollbackStrategy(Protocol):
    """Pure strategy — shapes plan fields only."""

    @property
    def kind(self) -> RollbackStrategyKind: ...

    def apply_plan(self, fields: Mapping[str, Any]) -> dict[str, Any]: ...


class _StrategyBase(_Frozen):
    """Frozen strategy envelope."""

    kind: RollbackStrategyKind
    level: RollbackLevel = RollbackLevel.WORKFLOW
    metadata: dict[str, Any] = Field(default_factory=dict)

    def apply_plan(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(fields)
        out["rollback_strategy"] = self.kind
        out["rollback_level"] = self.level
        if self.metadata:
            meta = dict(out.get("metadata") or {})
            meta.update(self.metadata)
            out["metadata"] = meta
        return out


class ResumeCheckpointStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.RESUME_CHECKPOINT
    level: RollbackLevel = RollbackLevel.WORKFLOW


class RestartWorkflowStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.RESTART_WORKFLOW
    level: RollbackLevel = RollbackLevel.WORKFLOW


class RestartNodeStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.RESTART_NODE
    level: RollbackLevel = RollbackLevel.NODE

    def apply_plan(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        out = super().apply_plan(fields)
        node = out.get("target_node") or (out.get("target_nodes") or [None])[0]
        if node:
            out["target_node"] = node
            out.setdefault("target_nodes", [node])
        return out


class RestartSubgraphStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.RESTART_SUBGRAPH
    level: RollbackLevel = RollbackLevel.SUBGRAPH


class RollbackContextStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.ROLLBACK_CONTEXT
    level: RollbackLevel = RollbackLevel.CONTEXT


class RollbackBudgetStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.ROLLBACK_BUDGET
    level: RollbackLevel = RollbackLevel.BUDGET


class RollbackMetadataStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.ROLLBACK_METADATA
    level: RollbackLevel = RollbackLevel.EXECUTION_METADATA


class CustomStrategy(_StrategyBase):
    kind: RollbackStrategyKind = RollbackStrategyKind.CUSTOM
    level: RollbackLevel = RollbackLevel.WORKFLOW
    strategy_id: str = "custom"
    overrides: dict[str, Any] = Field(default_factory=dict)

    def apply_plan(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        out = super().apply_plan(fields)
        out.update(self.overrides)
        meta = dict(out.get("metadata") or {})
        meta["custom_strategy_id"] = self.strategy_id
        out["metadata"] = meta
        out["rollback_strategy"] = RollbackStrategyKind.CUSTOM
        return out


_STRATEGY_BY_KIND: dict[RollbackStrategyKind, type[_StrategyBase]] = {
    RollbackStrategyKind.RESUME_CHECKPOINT: ResumeCheckpointStrategy,
    RollbackStrategyKind.RESTART_WORKFLOW: RestartWorkflowStrategy,
    RollbackStrategyKind.RESTART_NODE: RestartNodeStrategy,
    RollbackStrategyKind.RESTART_SUBGRAPH: RestartSubgraphStrategy,
    RollbackStrategyKind.ROLLBACK_CONTEXT: RollbackContextStrategy,
    RollbackStrategyKind.ROLLBACK_BUDGET: RollbackBudgetStrategy,
    RollbackStrategyKind.ROLLBACK_METADATA: RollbackMetadataStrategy,
    RollbackStrategyKind.CUSTOM: CustomStrategy,
}


def strategy_for(
    kind: RollbackStrategyKind | str,
    **kwargs: Any,
) -> _StrategyBase:
    """Factory for pure strategy objects."""
    if isinstance(kind, str):
        kind = RollbackStrategyKind(kind)
    cls = _STRATEGY_BY_KIND[kind]
    return cls.model_validate(kwargs) if kwargs else cls()


__all__ = [
    "IRollbackStrategy",
    "ResumeCheckpointStrategy",
    "RestartWorkflowStrategy",
    "RestartNodeStrategy",
    "RestartSubgraphStrategy",
    "RollbackContextStrategy",
    "RollbackBudgetStrategy",
    "RollbackMetadataStrategy",
    "CustomStrategy",
    "strategy_for",
]
