"""Serialize / deserialize WorkflowExecution."""

from __future__ import annotations

import json
from typing import Any

from .exceptions import SerializationError
from .models import WorkflowExecution
from .workflow_state import WorkflowStatus


def _graph_to_dict(graph: Any) -> Any:
    if graph is None:
        return None
    if hasattr(graph, "model_dump"):
        return graph.model_dump(mode="json")
    if isinstance(graph, dict):
        return graph
    raise SerializationError(f"unsupported graph type: {type(graph)!r}")


def _context_to_dict(context: Any) -> Any:
    if context is None:
        return None
    if hasattr(context, "model_dump"):
        return context.model_dump(mode="json")
    if isinstance(context, dict):
        return context
    if hasattr(context, "to_dict"):
        return context.to_dict()
    raise SerializationError(f"unsupported context type: {type(context)!r}")


def _rehydrate_graph(data: Any) -> Any:
    if data is None or not isinstance(data, dict):
        return data
    try:
        from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

        return TaskGraph.model_validate(data)
    except Exception:
        return data


class WorkflowSerializer:
    """JSON serializer for WorkflowExecution (graph/context as dicts)."""

    def dumps(self, execution: WorkflowExecution, *, indent: int | None = 2) -> str:
        try:
            payload = execution.model_dump(mode="json")
            payload["graph"] = _graph_to_dict(execution.graph)
            payload["context"] = _context_to_dict(execution.context)
            return json.dumps(payload, indent=indent, default=str)
        except Exception as exc:  # noqa: BLE001
            raise SerializationError(str(exc)) from exc

    def loads(self, raw: str) -> WorkflowExecution:
        try:
            data = json.loads(raw)
            if "status" in data and isinstance(data["status"], str):
                data["status"] = WorkflowStatus(data["status"])
            if isinstance(data.get("graph"), dict):
                data["graph"] = _rehydrate_graph(data["graph"])
            return WorkflowExecution.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise SerializationError(str(exc)) from exc


def dumps(execution: WorkflowExecution, *, indent: int | None = 2) -> str:
    return WorkflowSerializer().dumps(execution, indent=indent)


def loads(raw: str) -> WorkflowExecution:
    return WorkflowSerializer().loads(raw)
