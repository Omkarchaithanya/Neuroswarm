"""Immutable Task Graph execution-state snapshot (refs only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import _Frozen


class GraphSnapshot(_Frozen):
    """Frozen view of task-graph progress — node ids and statuses only."""

    snapshot_id: str = Field(default_factory=lambda: new_id("gsnap_"))
    graph_id: str = ""
    graph_reference: str | None = None
    node_statuses: dict[str, str] = Field(default_factory=dict)
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    skipped_nodes: list[str] = Field(default_factory=list)
    frontier_nodes: list[str] = Field(default_factory=list)
    subgraph_id: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _hash(self) -> GraphSnapshot:
        if self.content_hash:
            return self
        payload = {
            "graph_id": self.graph_id,
            "node_statuses": self.node_statuses,
            "completed_nodes": self.completed_nodes,
            "failed_nodes": self.failed_nodes,
            "skipped_nodes": self.skipped_nodes,
            "frontier_nodes": self.frontier_nodes,
            "subgraph_id": self.subgraph_id,
        }
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self
