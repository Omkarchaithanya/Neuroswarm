"""Async reconcile loop — ready → assign → dispatch → monitor → aggregate."""

from __future__ import annotations

import time
from typing import Any, Mapping

from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from .aggregation import ResultAggregator
from .assignment import AgentAssigner
from .checkpoint import CheckpointCoordinator
from .completion import CompletionEvaluator
from .dispatcher import Dispatcher
from .events import EventBus
from .exceptions import CoordinationError
from .interfaces import IHaoeExecutionPort
from .lifecycle import WorkflowLifecycle
from .metrics import OrchestratorMetrics
from .models import WorkflowExecution
from .monitor import ExecutionMonitor
from .node_selector import NodeSelector
from .progress import ProgressMonitor
from .readiness import ReadyNodeResolver
from .retry import RetryCoordinator
from .rollback import RollbackCoordinator
from .synchronization import BarrierSynchronizer
from .workflow_state import TERMINAL_WORKFLOW_STATUSES, WorkflowStatus


class Coordinator:
    """Kubernetes-controller style coordination loop."""

    def __init__(
        self,
        *,
        haoe: IHaoeExecutionPort,
        assigner: AgentAssigner | None = None,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
        dispatcher: Dispatcher | None = None,
        aggregator: ResultAggregator | None = None,
        retry: RetryCoordinator | None = None,
        rollback: RollbackCoordinator | None = None,
        checkpoint: CheckpointCoordinator | None = None,
        completion: CompletionEvaluator | None = None,
        lifecycle: WorkflowLifecycle | None = None,
        progress: ProgressMonitor | None = None,
        monitor: ExecutionMonitor | None = None,
        max_parallel: int | None = None,
        fail_fast: bool = False,
        auto_checkpoint: bool = False,
        poll_retries: int = 64,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or OrchestratorMetrics()
        self.lifecycle = lifecycle or WorkflowLifecycle()
        self.assigner = assigner or AgentAssigner(events=self.events, metrics=self.metrics)
        self.dispatcher = dispatcher or Dispatcher(haoe)
        self.aggregator = aggregator or ResultAggregator(events=self.events, metrics=self.metrics)
        self.retry = retry or RetryCoordinator(events=self.events, metrics=self.metrics)
        self.rollback = rollback or RollbackCoordinator(events=self.events)
        self.checkpoint = checkpoint or CheckpointCoordinator(
            events=self.events, metrics=self.metrics, lifecycle=self.lifecycle
        )
        self.completion = completion or CompletionEvaluator(
            events=self.events,
            metrics=self.metrics,
            lifecycle=self.lifecycle,
            fail_fast=fail_fast,
        )
        self.progress = progress or ProgressMonitor()
        self.monitor = monitor or ExecutionMonitor(events=self.events, metrics=self.metrics)
        self.max_parallel = max_parallel
        self.auto_checkpoint = auto_checkpoint
        self.poll_retries = poll_retries
        self.haoe = haoe

    async def coordinate(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Run reconcile loop until terminal status."""
        t0 = time.perf_counter()
        if execution.status == WorkflowStatus.CREATED:
            self.lifecycle.mark_ready(execution)
        if execution.status in {WorkflowStatus.READY, WorkflowStatus.RESTORED}:
            if execution.status == WorkflowStatus.RESTORED:
                self.lifecycle.mark_ready(execution)
            self.lifecycle.mark_running(execution)
            self.metrics.record_workflow_started()

        while execution.status not in TERMINAL_WORKFLOW_STATUSES:
            if execution.cancel_requested:
                await self._cancel_inflight()
                self.lifecycle.mark_cancelled(execution)
                break
            execution = await self.step(execution)
            if execution.status in TERMINAL_WORKFLOW_STATUSES:
                break
            # Idle wait state with no ready/running → finalize
            if (
                not execution.ready_nodes
                and not execution.current_nodes
                and not execution.pending_nodes
            ):
                execution = self.completion.finalize(execution)
                break
            if (
                not execution.ready_nodes
                and not execution.current_nodes
                and execution.pending_nodes
            ):
                # Deadlock / blocked — try skip conditional, else fail
                execution = self._try_skip_blocked(execution)
                if not execution.ready_nodes and execution.pending_nodes:
                    if execution.failed_nodes:
                        execution = self.completion.finalize(execution)
                        break
                    raise CoordinationError(
                        f"coordination stalled; pending={execution.pending_nodes}"
                    )

        elapsed = (time.perf_counter() - t0) * 1000.0
        execution.metrics.coordination_latency_ms = elapsed
        self.metrics.observe_coordination_latency(elapsed)
        return execution

    async def step(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Single reconcile tick."""
        graph = self._graph(execution)
        resolver = ReadyNodeResolver(graph)
        selector = NodeSelector(graph)
        sync = BarrierSynchronizer(graph, events=self.events)

        condition_ctx = self._condition_ctx(execution)
        ready = resolver.resolve(
            completed=execution.completed_nodes,
            failed=execution.failed_nodes,
            skipped=execution.skipped_nodes,
            running=execution.current_nodes,
            cancel_requested=execution.cancel_requested,
            condition_ctx=condition_ctx,
        )
        # Skip nodes whose conditions fail
        for nid in list(execution.pending_nodes):
            if nid in ready or nid in execution.current_nodes:
                continue
            if resolver.should_skip(
                nid, completed=execution.completed_nodes, condition_ctx=condition_ctx
            ):
                if nid not in execution.skipped_nodes:
                    execution.skipped_nodes.append(nid)
                execution.pending_nodes = [n for n in execution.pending_nodes if n != nid]

        ready = resolver.resolve(
            completed=execution.completed_nodes,
            failed=execution.failed_nodes,
            skipped=execution.skipped_nodes,
            running=execution.current_nodes,
            cancel_requested=execution.cancel_requested,
            condition_ctx=condition_ctx,
        )
        execution = self.progress.refresh_execution_sets(execution, ready=ready, graph=graph)

        # Release barriers that are satisfied
        for nid in list(ready):
            sync.release_if_ready(
                nid,
                completed=set(execution.completed_nodes) | set(execution.skipped_nodes),
                workflow_id=execution.workflow_id,
                execution_id=execution.execution_id,
            )

        to_dispatch = selector.select(ready, max_parallel=self.max_parallel)
        if to_dispatch and execution.status == WorkflowStatus.WAITING:
            self.lifecycle.mark_running(execution)

        # Assign + dispatch
        for nid in to_dispatch:
            node = graph.nodes[nid]
            assignment = self.assigner.assign(
                node,
                agent_pool=execution.agent_pool,
                context=self._context_map(execution),
                workflow_id=execution.workflow_id,
                execution_id=execution.execution_id,
            )
            execution.assigned_agents[nid] = assignment
            await self.dispatcher.dispatch(execution, assignment)
            execution = self.monitor.mark_running(execution, [nid])

        self.metrics.set_parallelism(float(len(execution.current_nodes)))
        if execution.agent_pool:
            util = len(execution.current_nodes) / max(1, len(execution.agent_pool))
            self.metrics.set_agent_utilization(min(1.0, util))
            execution.metrics.agent_utilization = min(1.0, util)

        # Poll inflight
        for request_id, req in list(self.dispatcher.inflight().items()):
            signal = None
            for _ in range(self.poll_retries):
                signal = await self.haoe.poll(request_id)
                if signal is not None:
                    break
            if signal is None:
                continue
            execution = self.monitor.apply_signal(execution, signal)
            self.dispatcher.drop(request_id)

            if signal.status.lower() in {"failed", "timed_out"}:
                node = graph.nodes[signal.node_id]
                decision = self.retry.decide(
                    node, execution=execution, error=signal.error
                )
                execution = self.retry.apply(execution, decision)
                if decision.skip:
                    plan = self.rollback.plan(
                        execution, target_nodes=[signal.node_id], reason=signal.error or "fail"
                    )
                    execution = self.rollback.notify(execution, plan)

        # Aggregate completed results
        if execution.node_results:
            execution.aggregated = self.aggregator.aggregate(
                execution.node_results,
                workflow_id=execution.workflow_id,
                execution_id=execution.execution_id,
            )

        # Re-resolve ready set after completions so next tick (or same loop) advances
        condition_ctx = self._condition_ctx(execution)
        ready = resolver.resolve(
            completed=execution.completed_nodes,
            failed=execution.failed_nodes,
            skipped=execution.skipped_nodes,
            running=execution.current_nodes,
            cancel_requested=execution.cancel_requested,
            condition_ctx=condition_ctx,
        )
        execution = self.progress.refresh_execution_sets(execution, ready=ready, graph=graph)

        if self.auto_checkpoint and execution.completed_nodes:
            # Checkpoint every tick when enabled (coordination only)
            if execution.status not in TERMINAL_WORKFLOW_STATUSES:
                try:
                    if execution.status in {
                        WorkflowStatus.RUNNING,
                        WorkflowStatus.WAITING,
                        WorkflowStatus.READY,
                    }:
                        self.checkpoint.create(execution)
                        # resume running after checkpoint
                        if execution.status == WorkflowStatus.CHECKPOINTED:
                            self.lifecycle.mark_restored(execution)
                            self.lifecycle.mark_running(execution)
                except Exception:  # noqa: BLE001
                    pass

        if self.completion.is_complete(execution) or self.completion.should_fail(execution):
            execution = self.completion.finalize(execution)
        elif not execution.current_nodes and execution.ready_nodes:
            if execution.status == WorkflowStatus.WAITING:
                self.lifecycle.mark_running(execution)
        elif not execution.current_nodes and execution.pending_nodes and not execution.ready_nodes:
            if execution.status == WorkflowStatus.RUNNING:
                self.lifecycle.mark_waiting(execution)
        elif execution.current_nodes or execution.ready_nodes:
            if execution.status == WorkflowStatus.WAITING:
                self.lifecycle.mark_running(execution)

        execution.touch()
        # Append recent events into execution.events bag
        for ev in self.events.history()[-20:]:
            d = ev.to_dict()
            if d not in execution.events:
                execution.events.append(d)
        return execution

    def _try_skip_blocked(self, execution: WorkflowExecution) -> WorkflowExecution:
        graph = self._graph(execution)
        resolver = ReadyNodeResolver(graph)
        ctx = self._condition_ctx(execution)
        changed = False
        for nid in list(execution.pending_nodes):
            if resolver.should_skip(
                nid, completed=execution.completed_nodes, condition_ctx=ctx
            ):
                if nid not in execution.skipped_nodes:
                    execution.skipped_nodes.append(nid)
                execution.pending_nodes = [n for n in execution.pending_nodes if n != nid]
                changed = True
        if changed:
            ready = resolver.resolve(
                completed=execution.completed_nodes,
                failed=execution.failed_nodes,
                skipped=execution.skipped_nodes,
                running=execution.current_nodes,
                condition_ctx=ctx,
            )
            execution = self.progress.refresh_execution_sets(execution, ready=ready, graph=graph)
        return execution

    async def _cancel_inflight(self) -> None:
        for request_id in list(self.dispatcher.inflight()):
            await self.dispatcher.cancel(request_id, forced=True)

    def _graph(self, execution: WorkflowExecution) -> TaskGraph:
        graph = execution.graph
        if not isinstance(graph, TaskGraph):
            raise CoordinationError("execution.graph must be a TaskGraph instance")
        return graph

    def _condition_ctx(self, execution: WorkflowExecution) -> dict[str, Any]:
        statuses: dict[str, str] = {}
        for nid in execution.completed_nodes:
            statuses[nid] = "succeeded"
        for nid in execution.failed_nodes:
            statuses[nid] = "failed"
        for nid in execution.skipped_nodes:
            statuses[nid] = "skipped"
        ctx: dict[str, Any] = {"node_statuses": statuses}
        if execution.context is not None and hasattr(execution.context, "as_condition_map"):
            try:
                ctx.update(dict(execution.context.as_condition_map()))
            except Exception:  # noqa: BLE001
                pass
        return ctx

    def _context_map(self, execution: WorkflowExecution) -> Mapping[str, Any]:
        ctx = execution.context
        if ctx is None:
            return {}
        if hasattr(ctx, "model_dump"):
            return ctx.model_dump(mode="json")
        if isinstance(ctx, Mapping):
            return ctx
        if hasattr(ctx, "to_dict"):
            return ctx.to_dict()
        return {"context_id": execution.context_id}
