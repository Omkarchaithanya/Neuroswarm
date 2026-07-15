"""Async-first Task Graph execution engine (lifecycle only — no agent/DIPA)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .conditions import evaluate_condition
from .context import SwarmContext
from .dag import DAGAnalyzer
from .enums import CancelMode, GraphPhase, NodeStatus, NODE_TRANSITIONS, TERMINAL_STATUSES
from .events import (
    Cancellation,
    Checkpoint,
    EventBus,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
    RetryStarted,
    Timeout,
)
from .exceptions import (
    CancellationError,
    ExecutionError,
    InvalidTransitionError,
    TimeoutError as GraphTimeoutError,
)
from .graph import TaskGraph
from .interfaces import INodeHandler
from .metrics import GraphMetrics, compute_static_metrics, tally_terminal_statuses
from .validator import validate_graph


@dataclass
class NodeRuntimeState:
    status: NodeStatus = NodeStatus.PENDING
    attempts: int = 0
    result: Any = None
    error: str | None = None
    queued_at: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    checkpoint_id: str | None = None
    cancel_requested: bool = False

    def transition(self, node_id: str, target: NodeStatus) -> None:
        allowed = NODE_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed and target is not self.status:
            # Allow PENDING -> SKIPPED already; FAILED -> RETRYING etc.
            if target not in allowed:
                raise InvalidTransitionError(node_id, self.status, target)
        self.status = target


@dataclass
class ExecutionState:
    """Mutable execution state — separate from immutable graph definition."""

    graph_id: str
    phase: GraphPhase = GraphPhase.IDLE
    nodes: dict[str, NodeRuntimeState] = field(default_factory=dict)
    context: SwarmContext = field(default_factory=SwarmContext)
    metrics: GraphMetrics = field(default_factory=GraphMetrics)
    cancel_mode: CancelMode | None = None
    cancel_forced: bool = False
    cancel_node_id: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None

    @classmethod
    def from_graph(cls, graph: TaskGraph, context: SwarmContext | None = None) -> ExecutionState:
        nodes = {nid: NodeRuntimeState(checkpoint_id=n.checkpoint_id) for nid, n in graph.nodes.items()}
        metrics = compute_static_metrics(graph)
        return cls(
            graph_id=graph.graph_id,
            nodes=nodes,
            context=context or SwarmContext(),
            metrics=metrics,
        )

    def statuses(self) -> dict[str, NodeStatus]:
        return {nid: st.status for nid, st in self.nodes.items()}

    def results(self) -> dict[str, Any]:
        return {nid: st.result for nid, st in self.nodes.items() if st.result is not None}


@dataclass
class ExecutionResult:
    state: ExecutionState
    succeeded: bool
    output: Any = None

    @property
    def phase(self) -> GraphPhase:
        return self.state.phase


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False
        self._forced = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def forced(self) -> bool:
        return self._forced

    def cancel(self, *, forced: bool = False) -> None:
        self._cancelled = True
        self._forced = forced or self._forced

    def throw_if_cancelled(self) -> None:
        if self._cancelled:
            raise CancellationError("cancelled", forced=self._forced)


class GraphExecutor:
    """Walk ready layers; apply conditions, retry, timeout, cancellation."""

    def __init__(
        self,
        *,
        event_bus: EventBus | None = None,
        fail_fast: bool = True,
        sleep: Any = None,
    ) -> None:
        self.events = event_bus or EventBus()
        self.fail_fast = fail_fast
        self._sleep = sleep or asyncio.sleep
        self._token = CancellationToken()
        self._state: ExecutionState | None = None
        self._analyzer: DAGAnalyzer | None = None

    @property
    def state(self) -> ExecutionState | None:
        return self._state

    def cancel(
        self,
        mode: CancelMode = CancelMode.GRAPH,
        *,
        node_id: str | None = None,
        forced: bool = False,
    ) -> None:
        self._token.cancel(forced=forced)
        if self._state is not None:
            self._state.cancel_mode = mode
            self._state.cancel_forced = forced
            self._state.cancel_node_id = node_id
            self.events.emit(
                Cancellation(
                    self._state.graph_id,
                    node_id,
                    mode=mode.value,
                    forced=forced,
                )
            )
            self._apply_cancel(mode, node_id=node_id, forced=forced)

    def _apply_cancel(
        self,
        mode: CancelMode,
        *,
        node_id: str | None,
        forced: bool,
    ) -> None:
        assert self._state is not None and self._analyzer is not None
        targets: set[str] = set()
        if mode is CancelMode.GRAPH:
            targets = set(self._state.nodes)
        elif mode is CancelMode.NODE and node_id:
            targets = {node_id}
        elif mode is CancelMode.SUBTREE and node_id:
            targets = self._analyzer.subtree(node_id)
        elif mode is CancelMode.DOWNSTREAM and node_id:
            targets = self._analyzer.downstream(node_id) | {node_id}
        for nid in targets:
            st = self._state.nodes[nid]
            if st.status in TERMINAL_STATUSES:
                continue
            st.cancel_requested = True
            if forced or st.status in {
                NodeStatus.PENDING,
                NodeStatus.QUEUED,
                NodeStatus.READY,
                NodeStatus.WAITING,
                NodeStatus.RETRYING,
            }:
                st.status = NodeStatus.CANCELLED
                st.finished_at = time.monotonic()

    async def run(
        self,
        graph: TaskGraph,
        handlers: Mapping[str, INodeHandler] | None = None,
        *,
        context: SwarmContext | None = None,
        validate: bool = True,
    ) -> ExecutionResult:
        if validate:
            report = validate_graph(graph)
            if not report.ok:
                raise ExecutionError(report.format())

        frozen = graph if graph.frozen else graph.clone()
        if not frozen.frozen:
            frozen.freeze()

        self._token = CancellationToken()
        self._analyzer = DAGAnalyzer(frozen)
        self._state = ExecutionState.from_graph(frozen, context)
        state = self._state
        state.phase = GraphPhase.RUNNING
        state.started_at = time.monotonic()
        handlers = handlers or {}

        workflow_deadline = None
        if frozen.timeout_policy.workflow_timeout_s:
            workflow_deadline = state.started_at + frozen.timeout_policy.workflow_timeout_s

        completed: set[str] = set()
        try:
            while len(completed) < len(frozen.nodes):
                self._token.throw_if_cancelled()
                if workflow_deadline and time.monotonic() > workflow_deadline:
                    self._timeout_remaining(frozen, completed, scope="workflow")
                    break

                ready = [
                    nid
                    for nid in self._analyzer.ready_nodes(completed)
                    if state.nodes[nid].status
                    not in TERMINAL_STATUSES | {NodeStatus.RUNNING, NodeStatus.RETRYING}
                ]
                # also pick up cancelled already marked
                for nid, st in state.nodes.items():
                    if st.status is NodeStatus.CANCELLED and nid not in completed:
                        completed.add(nid)

                if not ready:
                    # progress only via already-terminal?
                    pending = [
                        nid
                        for nid, st in state.nodes.items()
                        if nid not in completed and st.status not in TERMINAL_STATUSES
                    ]
                    if not pending:
                        break
                    # Soft-skip nodes whose conditions fail once preds done
                    progressed = False
                    for nid in list(pending):
                        preds = self._analyzer.predecessors(nid)
                        if all(p in completed for p in preds):
                            if not self._should_run(frozen, nid, state):
                                await self._skip(frozen, nid, state)
                                completed.add(nid)
                                progressed = True
                    if not progressed:
                        # deadlock / waiting on cancel
                        if self._token.is_cancelled():
                            break
                        raise ExecutionError("no ready nodes; graph may be stuck")
                    continue

                # parallel layer
                await asyncio.gather(
                    *[
                        self._run_node(frozen, nid, handlers, state, workflow_deadline)
                        for nid in ready
                    ]
                )
                for nid in ready:
                    if state.nodes[nid].status in TERMINAL_STATUSES:
                        completed.add(nid)
                        if (
                            self.fail_fast
                            and state.nodes[nid].status is NodeStatus.FAILED
                        ):
                            state.phase = GraphPhase.FAILED
                            state.error = state.nodes[nid].error
                            # cancel remaining
                            self.cancel(CancelMode.GRAPH, forced=False)
                            for oid, ost in state.nodes.items():
                                if oid not in completed and ost.status not in TERMINAL_STATUSES:
                                    ost.status = NodeStatus.CANCELLED
                                    completed.add(oid)
                            break

            state.finished_at = time.monotonic()
            state.metrics.execution_time_s = state.finished_at - (state.started_at or state.finished_at)
            tally_terminal_statuses(state.metrics, state.statuses())

            if state.phase is GraphPhase.FAILED:
                return ExecutionResult(state=state, succeeded=False)
            if any(s is NodeStatus.CANCELLED for s in state.statuses().values()) and self._token.is_cancelled():
                state.phase = GraphPhase.CANCELLED
                return ExecutionResult(state=state, succeeded=False)
            if any(s is NodeStatus.TIMED_OUT for s in state.statuses().values()):
                state.phase = GraphPhase.TIMED_OUT
                return ExecutionResult(state=state, succeeded=False)
            if any(s is NodeStatus.FAILED for s in state.statuses().values()):
                state.phase = GraphPhase.FAILED
                return ExecutionResult(state=state, succeeded=False)

            state.phase = GraphPhase.SUCCEEDED
            output = self._pick_output(frozen, state)
            return ExecutionResult(state=state, succeeded=True, output=output)
        except CancellationError:
            state.phase = GraphPhase.CANCELLED
            state.finished_at = time.monotonic()
            tally_terminal_statuses(state.metrics, state.statuses())
            return ExecutionResult(state=state, succeeded=False)
        except GraphTimeoutError as exc:
            state.phase = GraphPhase.TIMED_OUT
            state.error = str(exc)
            state.finished_at = time.monotonic()
            tally_terminal_statuses(state.metrics, state.statuses())
            return ExecutionResult(state=state, succeeded=False)

    def run_sync(
        self,
        graph: TaskGraph,
        handlers: Mapping[str, INodeHandler] | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        return asyncio.get_event_loop().run_until_complete(
            self.run(graph, handlers, **kwargs)
        ) if False else asyncio.run(self.run(graph, handlers, **kwargs))  # noqa: SIM222

    def _pick_output(self, graph: TaskGraph, state: ExecutionState) -> Any:
        for name in ("response", "aggregate", "output"):
            for nid, node in graph.nodes.items():
                if node.name == name and state.nodes[nid].status is NodeStatus.SUCCEEDED:
                    return state.nodes[nid].result
        leaves = self._analyzer.leaves() if self._analyzer else []
        for nid in leaves:
            if state.nodes[nid].status is NodeStatus.SUCCEEDED:
                return state.nodes[nid].result
        return None

    def _should_run(self, graph: TaskGraph, node_id: str, state: ExecutionState) -> bool:
        node = graph.nodes[node_id]
        ctx = state.context.as_condition_map()
        ctx["node_statuses"] = {
            nid: st.status for nid, st in state.nodes.items()
        }
        ctx["node_results"] = state.results()
        # edge conditions from predecessors
        for edge in graph.edges:
            if edge.dst != node_id:
                continue
            if edge.condition and not evaluate_condition(edge.condition, ctx):
                return False
        if node.condition and not evaluate_condition(node.condition, ctx):
            return False
        return True

    async def _skip(self, graph: TaskGraph, node_id: str, state: ExecutionState) -> None:
        st = state.nodes[node_id]
        st.status = NodeStatus.SKIPPED
        st.finished_at = time.monotonic()
        self.events.emit(NodeSkipped(graph.graph_id, node_id))

    def _timeout_remaining(
        self, graph: TaskGraph, completed: set[str], *, scope: str
    ) -> None:
        assert self._state is not None
        self.events.emit(Timeout(graph.graph_id, attributes={"scope": scope}))
        for nid, st in self._state.nodes.items():
            if nid not in completed and st.status not in TERMINAL_STATUSES:
                st.status = NodeStatus.TIMED_OUT
                st.error = f"timeout:{scope}"
                st.finished_at = time.monotonic()
                completed.add(nid)

    async def _run_node(
        self,
        graph: TaskGraph,
        node_id: str,
        handlers: Mapping[str, INodeHandler],
        state: ExecutionState,
        workflow_deadline: float | None,
    ) -> None:
        node = graph.nodes[node_id]
        st = state.nodes[node_id]
        metrics = state.metrics.ensure_node(node_id)

        if st.cancel_requested or self._token.is_cancelled():
            st.status = NodeStatus.CANCELLED
            st.finished_at = time.monotonic()
            return

        if not self._should_run(graph, node_id, state):
            await self._skip(graph, node_id, state)
            return

        st.queued_at = st.queued_at or time.monotonic()
        st.status = NodeStatus.READY
        st.status = NodeStatus.RUNNING
        st.started_at = time.monotonic()
        if st.queued_at:
            metrics.queue_time_s += st.started_at - st.queued_at
        self.events.emit(NodeStarted(graph.graph_id, node_id))

        handler_key = node.handler_key or node.name or node_id
        handler = handlers.get(handler_key) or handlers.get(node_id)

        max_attempts = node.retry_policy.max_attempts
        last_error: BaseException | None = None

        while st.attempts < max_attempts:
            st.attempts += 1
            try:
                self._token.throw_if_cancelled()
                timeout = node.timeout
                if graph.timeout_policy.node_timeout_s:
                    timeout = min(
                        t for t in (timeout, graph.timeout_policy.node_timeout_s) if t
                    ) if timeout else graph.timeout_policy.node_timeout_s

                async def _call() -> Any:
                    ctx = state.context.as_condition_map()
                    ctx["node_id"] = node_id
                    ctx["node"] = node.definition_payload()
                    ctx["node_results"] = state.results()
                    if handler is None:
                        return None
                    result = handler(node_id, ctx)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result

                async def _cancellable_call() -> Any:
                    task = asyncio.create_task(_call())
                    try:
                        while True:
                            if self._token.is_cancelled() or st.cancel_requested:
                                task.cancel()
                                try:
                                    await task
                                except (asyncio.CancelledError, Exception):
                                    pass
                                raise CancellationError(
                                    "cancelled", forced=self._token.forced
                                )
                            done, _ = await asyncio.wait({task}, timeout=0.05)
                            if done:
                                return task.result()
                    finally:
                        if not task.done():
                            task.cancel()

                if timeout:
                    result = await asyncio.wait_for(_cancellable_call(), timeout=timeout)
                else:
                    result = await _cancellable_call()

                st.result = result
                st.status = NodeStatus.SUCCEEDED
                st.finished_at = time.monotonic()
                metrics.execution_time_s += st.finished_at - (st.started_at or st.finished_at)
                if node.node_type.value == "checkpoint" or node.checkpoint_id:
                    st.checkpoint_id = node.checkpoint_id or node_id
                    self.events.emit(Checkpoint(graph.graph_id, node_id, checkpoint_id=st.checkpoint_id))
                    st.status = NodeStatus.CHECKPOINTED
                    st.status = NodeStatus.SUCCEEDED
                self.events.emit(NodeFinished(graph.graph_id, node_id))
                return
            except asyncio.TimeoutError as exc:
                last_error = exc
                metrics.failures += 1
                state.metrics.failures += 1
                self.events.emit(Timeout(graph.graph_id, node_id, scope="node"))
                if node.retry_policy.retry_on_timeout and st.attempts < max_attempts:
                    st.status = NodeStatus.RETRYING
                    metrics.retries += 1
                    state.metrics.retries += 1
                    delay = node.retry_policy.delay_for(st.attempts - 1)
                    self.events.emit(RetryStarted(graph.graph_id, node_id, attempt=st.attempts))
                    await self._sleep(delay)
                    st.status = NodeStatus.RUNNING
                    continue
                st.status = NodeStatus.TIMED_OUT
                st.error = "timeout:node"
                st.finished_at = time.monotonic()
                return
            except CancellationError:
                st.status = NodeStatus.CANCELLED
                st.finished_at = time.monotonic()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                metrics.failures += 1
                state.metrics.failures += 1
                self.events.emit(NodeFailed(graph.graph_id, node_id, error=str(exc)))
                if node.retry_policy.retry_on_failure and st.attempts < max_attempts:
                    st.status = NodeStatus.RETRYING
                    metrics.retries += 1
                    state.metrics.retries += 1
                    delay = node.retry_policy.delay_for(st.attempts - 1)
                    self.events.emit(RetryStarted(graph.graph_id, node_id, attempt=st.attempts))
                    await self._sleep(delay)
                    st.status = NodeStatus.RUNNING
                    continue
                st.status = NodeStatus.FAILED
                st.error = str(exc)
                st.finished_at = time.monotonic()
                return

        st.status = NodeStatus.FAILED
        st.error = str(last_error) if last_error else "max attempts exceeded"
        st.finished_at = time.monotonic()
