"""Task Graph unit tests — cycles, layers, validation, conditions, exec, ser, adapter."""

from __future__ import annotations

import asyncio
import time

import pytest

from neuroswarm_arm.runtime.swarm.task_graph import (
    Always,
    And,
    BudgetThreshold,
    ConfidenceThreshold,
    Custom,
    Failure,
    GraphExecutor,
    Never,
    Not,
    Or,
    Success,
    TaskGraph,
    TaskGraphBuilder,
    TaskNode,
    ToolAvailability,
    WorkflowPlanner,
    dumps,
    loads,
    register_condition,
    to_ascii,
    to_dot,
    to_json_graph,
    to_mermaid,
    validate_graph,
)
from neuroswarm_arm.runtime.swarm.task_graph.adapters import from_haoe_graph, to_haoe_graph
from neuroswarm_arm.runtime.swarm.task_graph.conditions import clear_condition_registry
from neuroswarm_arm.runtime.swarm.task_graph.dag import DAGAnalyzer
from neuroswarm_arm.runtime.swarm.task_graph.enums import (
    EdgeKind,
    NodeStatus,
    SerializationFormat,
)
from neuroswarm_arm.runtime.swarm.task_graph.exceptions import (
    CycleError,
    FrozenGraphError,
    ValidationError,
)
from neuroswarm_arm.runtime.swarm.task_graph.models import RetryPolicy
from neuroswarm_arm.runtime.swarm.task_graph.serializer import GraphSerializer


def _linear_graph() -> TaskGraph:
    return (
        TaskGraphBuilder(name="linear")
        .task("a", estimated_latency=10)
        .task("b", estimated_latency=20)
        .task("c", estimated_latency=5)
        .build()
    )


def test_cycle_detection() -> None:
    g = TaskGraph(name="cycle")
    a = g.add_node(TaskNode(name="a"))
    b = g.add_node(TaskNode(name="b"))
    g.add_edge(a, b)
    g.add_edge(b, a)
    assert g.has_cycle()
    with pytest.raises(CycleError):
        g.topological_sort()
    report = validate_graph(g)
    assert not report.ok
    assert any(i.code == "CYCLE" for i in report.issues)


def test_topological_sort_and_layers() -> None:
    g = (
        TaskGraphBuilder(name="fan")
        .task("root")
        .parallel("a", "b")
        .aggregate("join")
        .build()
    )
    order = g.topological_sort()
    assert len(order) == 4
    layers = g.execution_layers()
    assert len(layers) == 3
    assert len(layers[1]) == 2  # a, b parallel
    barriers = DAGAnalyzer(g).dependency_barriers()
    assert any(b["barrier_width"] == 2 for b in barriers)


def test_critical_path() -> None:
    g = _linear_graph()
    path = g.critical_path()
    assert len(path) == 3
    assert DAGAnalyzer(g).critical_path_latency_ms() == 35.0


def test_freeze_immutability() -> None:
    g = _linear_graph()
    assert g.frozen
    with pytest.raises(FrozenGraphError):
        g.add_node(TaskNode(name="x"))


def test_clone_and_hash() -> None:
    g = _linear_graph()
    h1 = g.content_hash()
    c = g.clone()
    assert c.graph_id != g.graph_id
    assert not c.frozen
    # same structure → same definition payload except graph_id
    c.graph_id = g.graph_id
    assert c.content_hash() == h1


def test_validation_disconnected_and_priority() -> None:
    g = TaskGraph(name="orphan")
    g.add_node(TaskNode(name="a"))
    g.add_node(TaskNode(name="b"))
    g.add_edge(list(g.nodes.keys())[0], list(g.nodes.keys())[0])  # self-loop after fix?
    # rebuild cleanly
    g = TaskGraph(name="orphan")
    n1 = g.add_node(TaskNode(name="a"))
    g.add_node(TaskNode(name="b"))
    g.add_edge(n1.id, n1.id)
    report = validate_graph(g)
    assert any(i.code == "SELF_LOOP" for i in report.issues)
    assert "DISCONNECTED" in report.format() or any(
        i.code == "DISCONNECTED_NODE" for i in report.issues
    )


def test_metadata_propagation() -> None:
    g = TaskGraph(name="meta")
    g.add_node(TaskNode(name="a"))
    g.propagate_metadata({"tenant": "arm"})
    node = next(iter(g.nodes.values()))
    assert node.metadata["tenant"] == "arm"
    assert g.metadata["tenant"] == "arm"


def test_conditions_composable() -> None:
    ctx = {
        "confidence": 0.9,
        "budget": {"cost_usd_used": 1.0},
        "available_tools": {"web"},
        "node_statuses": {"a": NodeStatus.SUCCEEDED},
    }
    cond = And(
        ConfidenceThreshold(0.8),
        BudgetThreshold(5.0),
        ToolAvailability("web"),
        Success("a"),
    )
    assert cond.evaluate(ctx)
    assert not (cond & Never()).evaluate(ctx)
    assert (Or(Never(), Always())).evaluate(ctx)
    assert Not(Never()).evaluate(ctx)
    assert Failure("a").evaluate({"node_statuses": {"a": NodeStatus.FAILED}})


def test_custom_condition_registry() -> None:
    clear_condition_registry()
    register_condition("ok", lambda ctx: ctx.get("flag") is True)
    c = Custom("ok")
    assert c.evaluate({"flag": True})
    assert c.to_dict()["name"] == "ok"
    clear_condition_registry()


def test_parallel_execution_layers() -> None:
    g = (
        TaskGraphBuilder(name="par")
        .task("root")
        .parallel("a", "b")
        .aggregate("join")
        .build()
    )
    seen: list[str] = []

    async def handler(node_id: str, ctx: dict) -> str:
        seen.append(node_id)
        await asyncio.sleep(0.01)
        return node_id

    handlers = {
        "root": handler,
        "a": handler,
        "b": handler,
        "join": handler,
    }

    async def _run() -> None:
        result = await GraphExecutor(sleep=asyncio.sleep).run(g, handlers)
        assert result.succeeded
        assert len(seen) == 4

    asyncio.run(_run())


def test_retry_on_failure() -> None:
    calls = {"n": 0}

    async def flaky(node_id: str, ctx: dict) -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    g = (
        TaskGraphBuilder(name="retry")
        .retry(max_attempts=5, backoff_base_s=0.0, jitter=False)
        .task("x", handler_key="x")
        .build()
    )
    for nid, node in list(g.unfreeze().nodes.items()):
        g.nodes[nid] = node.model_copy(
            update={"retry_policy": RetryPolicy(max_attempts=5, backoff_base_s=0.0, jitter=False)}
        )
    g.freeze()

    async def _run() -> None:
        result = await GraphExecutor(fail_fast=True).run(g, {"x": flaky})
        assert result.succeeded
        assert calls["n"] == 3
        assert result.state.metrics.retries >= 2

    asyncio.run(_run())


def test_cancellation_graph() -> None:
    started = asyncio.Event()

    async def slow(node_id: str, ctx: dict) -> str:
        started.set()
        await asyncio.sleep(10)
        return "done"

    g = TaskGraphBuilder(name="cancel").task("slow", handler_key="slow").build()
    ex = GraphExecutor()

    async def run_and_cancel():
        task = asyncio.create_task(ex.run(g, {"slow": slow}))
        await started.wait()
        ex.cancel(forced=True)
        return await task

    result = asyncio.run(run_and_cancel())
    assert not result.succeeded


def test_condition_skips_node() -> None:
    g = TaskGraph(name="skip")
    a = g.add_node(TaskNode(name="a", handler_key="a"))
    b = g.add_node(
        TaskNode(name="b", handler_key="b", condition=Never().to_dict())
    )
    g.add_edge(a, b)
    g.freeze()

    async def ok(node_id: str, ctx: dict) -> str:
        return "ok"

    async def _run() -> None:
        result = await GraphExecutor().run(g, {"a": ok, "b": ok})
        assert result.succeeded
        statuses = result.state.statuses()
        assert statuses[a.id] is NodeStatus.SUCCEEDED
        assert statuses[b.id] is NodeStatus.SKIPPED

    asyncio.run(_run())


def test_node_timeout() -> None:
    async def slow(node_id: str, ctx: dict) -> str:
        await asyncio.sleep(1.0)
        return "late"

    g = (
        TaskGraphBuilder(name="to")
        .timeout(0.05)
        .task("slow", handler_key="slow")
        .build()
    )

    async def _run() -> None:
        result = await GraphExecutor(fail_fast=False).run(g, {"slow": slow})
        assert not result.succeeded
        st = next(iter(result.state.nodes.values()))
        assert st.status is NodeStatus.TIMED_OUT

    asyncio.run(_run())


def test_serialization_json_yaml_pickle() -> None:
    g = _linear_graph()
    ser = GraphSerializer()
    raw = ser.dumps(g, fmt=SerializationFormat.JSON)
    g2 = ser.loads(raw, fmt=SerializationFormat.JSON)
    assert len(g2.nodes) == len(g.nodes)
    assert len(g2.edges) == len(g.edges)

    yraw = ser.dumps(g, fmt=SerializationFormat.YAML)
    g3 = ser.loads(yraw, fmt=SerializationFormat.YAML)
    assert len(g3.nodes) == 3

    praw = ser.dumps(g, fmt=SerializationFormat.PICKLE)
    g4 = ser.loads(praw, fmt=SerializationFormat.PICKLE)
    assert g4.name == g.name

    # module helpers
    g5 = loads(dumps(g))
    assert len(g5.nodes) == 3


def test_msgpack_soft_dep() -> None:
    g = _linear_graph()
    ser = GraphSerializer()
    try:
        import msgpack  # noqa: F401
    except ImportError:
        with pytest.raises(Exception):
            ser.dumps(g, fmt=SerializationFormat.MSGPACK)
    else:
        raw = ser.dumps(g, fmt=SerializationFormat.MSGPACK)
        g2 = ser.loads(raw, fmt=SerializationFormat.MSGPACK)
        assert len(g2.nodes) == 3


def test_visualization() -> None:
    g = _linear_graph()
    m = to_mermaid(g)
    assert "flowchart TD" in m
    d = to_dot(g)
    assert "digraph" in d
    a = to_ascii(g)
    assert "L0" in a
    j = to_json_graph(g)
    assert len(j["nodes"]) == 3


def test_planner_chat_and_multi() -> None:
    p = WorkflowPlanner()
    chat = p.plan_chat()
    assert "cascade" in {n.name for n in chat.nodes.values()}
    assert chat.frozen
    multi = p.plan_multi_agent()
    layers = multi.execution_layers()
    assert any(len(layer) == 3 for layer in layers)


def test_haoe_adapter_roundtrip() -> None:
    g = WorkflowPlanner().plan_chat(include_mem0=False, include_okf=False)
    hg = to_haoe_graph(g)
    assert len(hg.nodes) == len(g.nodes)
    assert len(hg.edges) == len(g.edges)
    back = from_haoe_graph(hg)
    assert len(back.nodes) == len(g.nodes)
    names = {n.name for n in back.nodes.values()}
    assert "semantic_route" in names
    assert "response" in names


def test_merge_split_subgraph() -> None:
    g1 = TaskGraphBuilder(name="a").task("x").build(freeze=False)
    g2 = TaskGraphBuilder(name="b").task("y").build(freeze=False)
    g1.merge(g2, prefix="p_")
    assert len(g1.nodes) == 2
    left, right = g1.split(list(g1.nodes.keys())[:1])
    assert len(left.nodes) == 1
    assert len(right.nodes) == 1
    sg = g1.extract_subgraph(list(g1.nodes.keys())[:1])
    assert len(sg.nodes) == 1


def test_builder_validate_fails_on_cycle() -> None:
    b = TaskGraphBuilder(name="bad")
    b.task("a")
    b.task("b")
    # manual cycle
    ids = list(b.graph.nodes.keys())
    b.graph.add_edge(ids[1], ids[0])
    with pytest.raises(ValidationError):
        b.build()


def test_performance_large_dag() -> None:
    b = TaskGraphBuilder(name="perf")
    b.task("n0")
    for i in range(1, 200):
        b.task(f"n{i}")
    t0 = time.perf_counter()
    g = b.build()
    _ = g.topological_sort()
    _ = g.execution_layers()
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0
    assert len(g.nodes) == 200
