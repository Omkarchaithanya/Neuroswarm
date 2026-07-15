"""Immutable execution-progress snapshot (refs only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import _Frozen


class ExecutionSnapshot(_Frozen):
    """Frozen execution progress — no live WorkflowExecution objects."""

    snapshot_id: str = Field(default_factory=lambda: new_id("esnap_"))
    execution_id: str = ""
    workflow_id: str = ""
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    skipped_nodes: list[str] = Field(default_factory=list)
    pending_nodes: list[str] = Field(default_factory=list)
    node_result_refs: dict[str, str] = Field(default_factory=dict)
    progress_ratio: float = 0.0
    experience_snapshot_ref: str | None = None
    execution_json_ref: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _hash(self) -> ExecutionSnapshot:
        if self.content_hash:
            return self
        payload = {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "completed_nodes": self.completed_nodes,
            "failed_nodes": self.failed_nodes,
            "skipped_nodes": self.skipped_nodes,
            "pending_nodes": self.pending_nodes,
            "node_result_refs": self.node_result_refs,
            "progress_ratio": self.progress_ratio,
            "experience_snapshot_ref": self.experience_snapshot_ref,
            "execution_json_ref": self.execution_json_ref,
        }
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self
