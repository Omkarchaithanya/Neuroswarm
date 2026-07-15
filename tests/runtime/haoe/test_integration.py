"""Integration tests for build_haoe + chat workflow + metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from neuroswarm_arm.metrics import MetricsStore
from neuroswarm_arm.runtime.haoe import build_haoe
from neuroswarm_arm.runtime.haoe.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.haoe.execution.task_executor import TaskExecutor
from neuroswarm_arm.runtime.haoe.interfaces.types import RuntimePhase
from neuroswarm_arm.runtime.haoe.workflow.cancellation import (
    CancellationManager,
    CancelledError,
)
from neuroswarm_arm.runtime.haoe.workflow.dag_builder import DAGBuilder
from neuroswarm_arm.runtime.haoe.workflow.workflow_executor import WorkflowExecutor

_ROOT = Path("work") / "test_haoe"


def _fresh(name: str) -> Path:
    path = _ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_build_haoe_schedule_and_metrics() -> None:
    bridge = MetricsStore()
    runtime = build_haoe(
        root=_fresh("metrics"),
        metrics_bridge=bridge,
        topology_cores=list(range(4)),
        fast_cores=[0, 1],
        slow_cores=[2, 3],
        start=True,
    )
    try:
        assert runtime.phase is RuntimePhase.RUNNING
        assert runtime.schedule(lambda: 7, priority="high") == 7
        exported = bridge.export_prometheus()
        assert "haoe_tasks_total" in exported or "haoe_workflows_total" in exported
        status = runtime.status()
        assert status["cpu_count"] == 4
        assert "features" in status
    finally:
        runtime.shutdown()
        assert runtime.phase is RuntimePhase.STOPPED


def test_chat_workflow_with_handlers() -> None:
    runtime = build_haoe(
        root=_fresh("chat"),
        topology_cores=list(range(2)),
        start=True,
    )
    try:
        handlers = {
            "semantic_route": lambda ctx: ["search"],
            "kv_session": lambda ctx: "sess-1",
            "cascade": lambda ctx: {"tier": 1, "text": "hello"},
            "kv_checkpoint": lambda ctx: "sess-1",
            "response": lambda ctx: {"tier": 1, "text": "hello"},
        }
        result = runtime.submit_workflow("chat", handlers)
        assert result.completed
        assert result.output == {"tier": 1, "text": "hello"}
        snap = runtime.performix.read_snapshot()
        assert snap is not None
        assert snap["source"] == "haoe"
    finally:
        runtime.shutdown()


def test_workflow_cancel_mid_flight() -> None:
    cancel_mgr = CancellationManager()
    token = cancel_mgr.create("wf-cancel")
    b = DAGBuilder(name="c")
    started = {"n": 0}

    def first(ctx: ExecutionContext) -> int:
        started["n"] += 1
        token.cancel()
        return 1

    def second(ctx: ExecutionContext) -> int:
        started["n"] += 10
        return 2

    a = b.node("a", first)
    c = b.node("c", second)
    b.sequence(a, c)
    ex = WorkflowExecutor(TaskExecutor(), cancellations=cancel_mgr)
    with pytest.raises(CancelledError):
        ex.execute(b.build(), token=token)
    assert started["n"] == 1
