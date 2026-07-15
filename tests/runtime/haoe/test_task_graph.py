"""Unit tests for task graph / DAG / cancellation / retry."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.haoe.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.haoe.execution.task_executor import TaskExecutor
from neuroswarm_arm.runtime.haoe.interfaces.types import EdgeKind, PriorityClass, RetryPolicy, TaskState
from neuroswarm_arm.runtime.haoe.workflow.cancellation import CancellationToken, CancelledError
from neuroswarm_arm.runtime.haoe.workflow.dag_builder import DAGBuilder
from neuroswarm_arm.runtime.haoe.workflow.dependency_graph import DependencyGraph
from neuroswarm_arm.runtime.haoe.workflow.retry_manager import RetryManager
from neuroswarm_arm.runtime.haoe.workflow.workflow_executor import WorkflowExecutor


def test_dag_fan_out_fan_in() -> None:
    b = DAGBuilder(name="fan")
    root = b.node("root", lambda ctx: "r")
    a = b.node("a", lambda ctx: "a")
    c = b.node("c", lambda ctx: "c")
    join = b.node("join", lambda ctx: "j")
    b.fan_out(root, a, c).fan_in(join, a, c)
    g = b.build()
    dep = DependencyGraph(g)
    assert dep.is_dag()
    assert dep.ready_nodes([]) == [root.node_id]
    assert set(dep.ready_nodes([root.node_id])) == {a.node_id, c.node_id}
    assert dep.ready_nodes([root.node_id, a.node_id, c.node_id]) == [join.node_id]


def test_critical_path_priority_inheritance() -> None:
    b = DAGBuilder(name="cp")
    n1 = b.node("n1", lambda ctx: 1)
    n2 = b.node("n2", lambda ctx: 2)
    n1.estimate.expected_latency_ms = 10
    n2.estimate.expected_latency_ms = 100
    n2.priority = PriorityClass.BACKGROUND
    b.sequence(n1, n2)
    g = b.build()
    dep = DependencyGraph(g)
    path = dep.critical_path()
    assert n2.node_id in path
    dep.inherit_priorities()
    assert g.nodes[n2.node_id].priority <= PriorityClass.HIGH


def test_conditional_edge_skips() -> None:
    b = DAGBuilder(name="cond")
    a = b.node("a", lambda ctx: 1)
    b_node = b.node("b", lambda ctx: 2)
    b.edge(a, b_node, kind=EdgeKind.CONDITIONAL, condition=lambda ctx: False)
    g = b.build()
    g.context["x"] = 1
    dep = DependencyGraph(g)
    assert dep.ready_nodes([a.node_id]) == []


def test_cancellation_token() -> None:
    token = CancellationToken()
    assert not token.is_cancelled()
    token.cancel()
    assert token.is_cancelled()
    with pytest.raises(CancelledError):
        token.throw_if_cancelled()


def test_retry_manager_succeeds() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    mgr = RetryManager(RetryPolicy(max_attempts=5, backoff_base_s=0.0))
    assert mgr.run(flaky) == "ok"
    assert mgr.retry_count == 2


def test_workflow_executor_runs_sequence() -> None:
    b = DAGBuilder(name="seq")
    seen: list[str] = []

    def make(name: str):
        def _fn(ctx: ExecutionContext) -> str:
            seen.append(name)
            return name

        return _fn

    a = b.node("a", make("a"))
    b_node = b.node("b", make("b"))
    b.sequence(a, b_node)
    ex = WorkflowExecutor(TaskExecutor(thread_workers=2, process_workers=0))
    result = ex.execute(b.build())
    assert result.completed
    assert seen == ["a", "b"]
