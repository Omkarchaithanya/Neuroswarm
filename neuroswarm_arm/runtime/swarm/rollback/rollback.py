"""RollbackOperation domain model + fluent RollbackBuilder."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import (
    ArtifactReference,
    InitiatorKind,
    RollbackLevel,
    RollbackStatus,
    RollbackStrategyKind,
    _Frozen,
)
from .versioning import SCHEMA_VERSION


class RollbackOperation(_Frozen):
    """Immutable rollback operation — consistency restoration unit.

    Not checkpoint restore. Not save/load. Not undo(). Deterministic workflow
    recovery descriptor that restores runtime consistency after partial failure.
    """

    rollback_id: str = Field(default_factory=lambda: new_id("rb_"))
    workflow_id: str
    execution_id: str
    checkpoint_reference: str | None = None
    recovery_plan_reference: str | None = None
    rollback_strategy: RollbackStrategyKind = RollbackStrategyKind.RESUME_CHECKPOINT
    rollback_level: RollbackLevel = RollbackLevel.WORKFLOW
    rollback_reason: str = ""
    initiator: InitiatorKind = InitiatorKind.SYSTEM
    timestamp: datetime = Field(default_factory=utc_now)
    target_node: str | None = None
    target_subgraph: str | None = None
    target_context: str | None = None
    target_budget: str | None = None
    target_nodes: list[str] = Field(default_factory=list)
    artifact_refs: list[ArtifactReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: RollbackStatus = RollbackStatus.PENDING
    version: int = SCHEMA_VERSION
    history: list[str] = Field(default_factory=list)
    checksum: str | None = None

    @model_validator(mode="after")
    def _ensure_checksum(self) -> Self:
        if self.checksum:
            return self
        payload = self.model_dump(mode="json", exclude={"checksum"})
        object.__setattr__(self, "checksum", stable_hash(payload))
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"checksum"})
        return stable_hash(payload)

    def verify_checksum(self) -> bool:
        if not self.checksum:
            return False
        return self.checksum == self.content_hash()

    def with_status(self, status: RollbackStatus) -> RollbackOperation:
        data = self.model_dump(mode="python")
        data["status"] = status
        data["checksum"] = None
        return RollbackOperation.model_validate(data)


class RollbackBuilder:
    """Fluent builder for RollbackOperation."""

    def __init__(self) -> None:
        self._workflow_id: str | None = None
        self._execution_id: str | None = None
        self._checkpoint_reference: str | None = None
        self._recovery_plan_reference: str | None = None
        self._strategy: RollbackStrategyKind = RollbackStrategyKind.RESUME_CHECKPOINT
        self._level: RollbackLevel = RollbackLevel.WORKFLOW
        self._reason: str = ""
        self._initiator: InitiatorKind = InitiatorKind.SYSTEM
        self._target_node: str | None = None
        self._target_subgraph: str | None = None
        self._target_context: str | None = None
        self._target_budget: str | None = None
        self._target_nodes: list[str] = []
        self._artifact_refs: list[ArtifactReference] = []
        self._metadata: dict[str, Any] = {}
        self._history: list[str] = []
        self._rollback_id: str | None = None

    def workflow(self, workflow_id: str, *, execution_id: str | None = None) -> Self:
        self._workflow_id = workflow_id
        if execution_id is not None:
            self._execution_id = execution_id
        return self

    def execution(self, execution_id: str) -> Self:
        self._execution_id = execution_id
        return self

    def checkpoint(self, checkpoint_reference: str | None) -> Self:
        self._checkpoint_reference = checkpoint_reference
        return self

    def recovery_plan(self, recovery_plan_reference: str | None) -> Self:
        self._recovery_plan_reference = recovery_plan_reference
        return self

    def strategy(self, strategy: RollbackStrategyKind | str) -> Self:
        if isinstance(strategy, str):
            strategy = RollbackStrategyKind(strategy)
        self._strategy = strategy
        return self

    def level(self, level: RollbackLevel | str) -> Self:
        if isinstance(level, str):
            level = RollbackLevel(level)
        self._level = level
        return self

    def reason(self, reason: str) -> Self:
        self._reason = reason
        return self

    def initiator(self, initiator: InitiatorKind | str) -> Self:
        if isinstance(initiator, str):
            initiator = InitiatorKind(initiator)
        self._initiator = initiator
        return self

    def node(self, node_id: str | None) -> Self:
        self._target_node = node_id
        return self

    def subgraph(self, subgraph_id: str | None) -> Self:
        self._target_subgraph = subgraph_id
        return self

    def context(self, context_id: str | None) -> Self:
        self._target_context = context_id
        return self

    def budget(self, budget_envelope_id: str | None) -> Self:
        self._target_budget = budget_envelope_id
        return self

    def targets(self, *node_ids: str) -> Self:
        self._target_nodes = list(node_ids)
        return self

    def artifact(self, ref: ArtifactReference) -> Self:
        self._artifact_refs.append(ref)
        return self

    def meta(self, **kwargs: Any) -> Self:
        self._metadata.update(kwargs)
        return self

    def history_refs(self, *rollback_ids: str) -> Self:
        self._history = list(rollback_ids)
        return self

    def rollback_id(self, rollback_id: str) -> Self:
        self._rollback_id = rollback_id
        return self

    def build(self) -> RollbackOperation:
        if not self._workflow_id:
            raise ValueError("workflow_id required")
        if not self._execution_id:
            raise ValueError("execution_id required")
        kwargs: dict[str, Any] = {
            "workflow_id": self._workflow_id,
            "execution_id": self._execution_id,
            "checkpoint_reference": self._checkpoint_reference,
            "recovery_plan_reference": self._recovery_plan_reference,
            "rollback_strategy": self._strategy,
            "rollback_level": self._level,
            "rollback_reason": self._reason,
            "initiator": self._initiator,
            "target_node": self._target_node,
            "target_subgraph": self._target_subgraph,
            "target_context": self._target_context,
            "target_budget": self._target_budget,
            "target_nodes": list(self._target_nodes),
            "artifact_refs": list(self._artifact_refs),
            "metadata": dict(self._metadata),
            "history": list(self._history),
        }
        if self._rollback_id:
            kwargs["rollback_id"] = self._rollback_id
        return RollbackOperation.model_validate(kwargs)
