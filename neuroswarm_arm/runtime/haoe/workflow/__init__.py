"""Workflow package — lazy re-exports to avoid import cycles with execution/."""

from __future__ import annotations

from typing import Any

__all__ = [
    "CancellationManager",
    "CancellationToken",
    "CancelledError",
    "CheckpointStore",
    "DAGBuilder",
    "DependencyGraph",
    "WorkflowPlanner",
    "RetryManager",
    "WorkflowExecutor",
    "WorkflowResult",
]


def __getattr__(name: str) -> Any:
    if name in {"CancellationManager", "CancellationToken", "CancelledError"}:
        from .cancellation import CancellationManager, CancellationToken, CancelledError

        return {
            "CancellationManager": CancellationManager,
            "CancellationToken": CancellationToken,
            "CancelledError": CancelledError,
        }[name]
    if name == "CheckpointStore":
        from .checkpointing import CheckpointStore

        return CheckpointStore
    if name == "DAGBuilder":
        from .dag_builder import DAGBuilder

        return DAGBuilder
    if name == "DependencyGraph":
        from .dependency_graph import DependencyGraph

        return DependencyGraph
    if name == "WorkflowPlanner":
        from .planner import WorkflowPlanner

        return WorkflowPlanner
    if name == "RetryManager":
        from .retry_manager import RetryManager

        return RetryManager
    if name in {"WorkflowExecutor", "WorkflowResult"}:
        from .workflow_executor import WorkflowExecutor, WorkflowResult

        return {"WorkflowExecutor": WorkflowExecutor, "WorkflowResult": WorkflowResult}[name]
    raise AttributeError(name)
