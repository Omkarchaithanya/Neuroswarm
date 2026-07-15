"""Immutable Checkpoint model + fluent CheckpointBuilder."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .budget_snapshot import BudgetSnapshot
from .context_snapshot import ContextSnapshot
from .execution_snapshot import ExecutionSnapshot
from .graph_snapshot import GraphSnapshot
from .models import ArtifactReference, CheckpointLevel, CheckpointStatus, _Frozen
from .snapshot import MetricsSnapshot
from .versioning import SCHEMA_VERSION


class Checkpoint(_Frozen):
    """Immutable durable recovery point for workflow fault tolerance.

    Stores references and frozen snapshots only — never live objects or threads.
    """

    checkpoint_id: str = Field(default_factory=lambda: new_id("ckpt_"))
    workflow_id: str
    execution_id: str
    parent_checkpoint: str | None = None
    checkpoint_level: CheckpointLevel = CheckpointLevel.AUTOMATIC
    timestamp: datetime = Field(default_factory=utc_now)
    graph_reference: str | None = None
    execution_snapshot: ExecutionSnapshot | None = None
    context_snapshot: ContextSnapshot | None = None
    budget_snapshot: BudgetSnapshot | None = None
    metrics_snapshot: MetricsSnapshot | None = None
    graph_snapshot: GraphSnapshot | None = None
    artifact_references: list[ArtifactReference] = Field(default_factory=list)
    experience_reference: str | None = None
    trace_reference: str | None = None
    version: int = SCHEMA_VERSION
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: CheckpointStatus = CheckpointStatus.ACTIVE

    @model_validator(mode="after")
    def _checksum(self) -> Checkpoint:
        if self.checksum:
            return self
        object.__setattr__(self, "checksum", self.compute_checksum())
        return self

    def compute_checksum(self) -> str:
        payload = self.model_dump(mode="json", exclude={"checksum"})
        return stable_hash(payload)

    def verify_checksum(self) -> bool:
        return self.checksum == self.compute_checksum()

    def clone(self, **overrides: Any) -> Checkpoint:
        """Return a new Checkpoint with a fresh id (and recomputed checksum)."""
        data = self.model_dump(mode="python")
        data.pop("checksum", None)
        data["checkpoint_id"] = new_id("ckpt_")
        data["timestamp"] = utc_now()
        data["parent_checkpoint"] = self.checkpoint_id
        data.update(overrides)
        data["checksum"] = None
        return Checkpoint.model_validate(data)


class CheckpointBuilder:
    """Fluent builder for production Checkpoint instances."""

    def __init__(self, *, validate: bool = True) -> None:
        self._validate = validate
        self._data: dict[str, Any] = {}

    def workflow(
        self,
        workflow_id: str,
        *,
        execution_id: str | None = None,
    ) -> CheckpointBuilder:
        self._data["workflow_id"] = workflow_id
        if execution_id is not None:
            self._data["execution_id"] = execution_id
        return self

    def execution(
        self,
        execution_id: str | None = None,
        *,
        snapshot: ExecutionSnapshot | None = None,
    ) -> CheckpointBuilder:
        if execution_id is not None:
            self._data["execution_id"] = execution_id
        if snapshot is not None:
            self._data["execution_snapshot"] = snapshot
        return self

    def context(self, snapshot: ContextSnapshot) -> CheckpointBuilder:
        self._data["context_snapshot"] = snapshot
        return self

    def budget(self, snapshot: BudgetSnapshot) -> CheckpointBuilder:
        self._data["budget_snapshot"] = snapshot
        return self

    def metrics(self, snapshot: MetricsSnapshot) -> CheckpointBuilder:
        self._data["metrics_snapshot"] = snapshot
        return self

    def graph(
        self,
        *,
        reference: str | None = None,
        snapshot: GraphSnapshot | None = None,
    ) -> CheckpointBuilder:
        if reference is not None:
            self._data["graph_reference"] = reference
        if snapshot is not None:
            self._data["graph_snapshot"] = snapshot
            if snapshot.graph_reference and "graph_reference" not in self._data:
                self._data["graph_reference"] = snapshot.graph_reference
        return self

    def level(self, level: CheckpointLevel) -> CheckpointBuilder:
        self._data["checkpoint_level"] = level
        return self

    def parent(self, parent_checkpoint: str | None) -> CheckpointBuilder:
        self._data["parent_checkpoint"] = parent_checkpoint
        return self

    def experience(self, reference: str | None) -> CheckpointBuilder:
        self._data["experience_reference"] = reference
        return self

    def trace(self, reference: str | None) -> CheckpointBuilder:
        self._data["trace_reference"] = reference
        return self

    def artifacts(self, refs: list[ArtifactReference]) -> CheckpointBuilder:
        self._data["artifact_references"] = list(refs)
        return self

    def metadata(self, **kwargs: Any) -> CheckpointBuilder:
        meta = dict(self._data.get("metadata") or {})
        meta.update(kwargs)
        self._data["metadata"] = meta
        return self

    def ids(
        self,
        *,
        checkpoint_id: str | None = None,
        parent_checkpoint: str | None = None,
    ) -> CheckpointBuilder:
        if checkpoint_id is not None:
            self._data["checkpoint_id"] = checkpoint_id
        if parent_checkpoint is not None:
            self._data["parent_checkpoint"] = parent_checkpoint
        return self

    def build(self) -> Checkpoint:
        if "workflow_id" not in self._data:
            raise ValueError("workflow_id required")
        if "execution_id" not in self._data:
            raise ValueError("execution_id required")
        ckpt = Checkpoint.model_validate(self._data)
        if self._validate and not ckpt.verify_checksum():
            raise ValueError("checksum verification failed after build")
        return ckpt
