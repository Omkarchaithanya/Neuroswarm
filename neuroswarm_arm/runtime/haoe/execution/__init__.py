"""Execution package — lazy-friendly re-exports."""

from __future__ import annotations

from .async_executor import (
    AsyncExecutor,
    InlineExecutor,
    NativeExecutorStub,
    ProcessExecutor,
    ThreadExecutor,
    select_executor,
)
from .execution_context import (
    ExecutionContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)

# TaskExecutor imports workflow pieces; keep it importable without pulling planner.
def __getattr__(name: str):
    if name == "TaskExecutor":
        from .task_executor import TaskExecutor

        return TaskExecutor
    raise AttributeError(name)


__all__ = [
    "AsyncExecutor",
    "InlineExecutor",
    "NativeExecutorStub",
    "ProcessExecutor",
    "ThreadExecutor",
    "select_executor",
    "ExecutionContext",
    "get_current_context",
    "reset_current_context",
    "set_current_context",
    "TaskExecutor",
]
