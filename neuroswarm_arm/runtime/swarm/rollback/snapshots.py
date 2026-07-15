"""Rollback target snapshot references (refs only — no binary payloads)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .models import ArtifactReference, _Frozen


class GraphSnapshotRef(_Frozen):
    """Task Graph snapshot reference for consistency / rollback targets."""

    graph_id: str
    subgraph_id: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    frontier_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionSnapshotRef(_Frozen):
    """Execution snapshot reference."""

    execution_id: str
    workflow_id: str
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextSnapshotRef(_Frozen):
    """Swarm Context snapshot reference."""

    context_id: str
    context_snapshot_id: str | None = None
    version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetSnapshotRef(_Frozen):
    """ARMORA budget envelope snapshot reference."""

    envelope_id: str
    remaining_cost_usd: float | None = None
    remaining: dict[str, float | None] = Field(default_factory=dict)
    frozen: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetadataSnapshotRef(_Frozen):
    """Execution metadata snapshot reference."""

    execution_id: str
    keys: list[str] = Field(default_factory=list)
    version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackSnapshotBundle(_Frozen):
    """Bundle of rollback target refs (no payloads)."""

    graph: GraphSnapshotRef | None = None
    execution: ExecutionSnapshotRef | None = None
    context: ContextSnapshotRef | None = None
    budget: BudgetSnapshotRef | None = None
    exec_metadata: MetadataSnapshotRef | None = None
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    experience_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
