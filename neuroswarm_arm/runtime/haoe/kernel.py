"""HAOERuntime — the agent runtime kernel instance."""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable, Mapping

from .core.dispatcher import Dispatcher
from .core.workflow_scheduler import WorkflowScheduler
from .execution.execution_context import ExecutionContext
from .interfaces.types import (
    CorrelationIds,
    PoolKind,
    PriorityClass,
    RuntimePhase,
)
from .runtime.runtime_config import HAOERuntimeConfig
from .runtime.runtime_events import lifecycle_event
from .runtime.runtime_registry import RuntimeRegistry
from .runtime.runtime_state import RuntimeStateMachine
from .scheduling.load_balancer import LoadBalancer
from .scheduling.priority_scheduler import PriorityScheduler
from .scheduling.queue_manager import QueueManager
from .scheduling.work_stealing import WorkStealingScheduler
from .scheduling.worker_pool import WorkerPoolManager
from .telemetry.event_bus import EventBus
from .telemetry.metrics import HAOEMetrics
from .telemetry.performix_adapter import PerformixAdapter
from .telemetry.profiler import Profiler
from .topology.affinity_manager import AffinityManager
from .topology.topology_service import TopologyService
from .workflow.planner import WorkflowPlanner
from .workflow.workflow_executor import WorkflowResult


class HAOERuntime:
    """Production HAOE kernel. Coordinates inference; never performs it."""

    def __init__(
        self,
        config: HAOERuntimeConfig,
        *,
        topology: TopologyService,
        affinity: AffinityManager,
        queues: QueueManager,
        stealer: WorkStealingScheduler,
        scheduler: PriorityScheduler,
        pools: WorkerPoolManager,
        balancer: LoadBalancer,
        dispatcher: Dispatcher,
        workflow_scheduler: WorkflowScheduler,
        planner: WorkflowPlanner,
        event_bus: EventBus,
        metrics: HAOEMetrics,
        profiler: Profiler,
        performix: PerformixAdapter,
        registry: RuntimeRegistry,
        fast_cores: list[int] | None = None,
        slow_cores: list[int] | None = None,
    ) -> None:
        self.config = config
        self.topology = topology
        self.affinity = affinity
        self.queues = queues
        self.stealer = stealer
        self.scheduler = scheduler
        self.pools = pools
        self.balancer = balancer
        self.dispatcher = dispatcher
        self.workflow_scheduler = workflow_scheduler
        self.planner = planner
        self.event_bus = event_bus
        self.metrics = metrics
        self.profiler = profiler
        self.performix = performix
        self.registry = registry
        self.fast_cores = fast_cores or topology.fast_cores()
        self.slow_cores = slow_cores or topology.efficiency_cores()
        self._state = RuntimeStateMachine()
        self.last_numa_node = 0

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._state.phase is RuntimePhase.RUNNING:
            return
        self._state.transition(RuntimePhase.STARTING)
        self.pools.start_all()
        self._state.transition(RuntimePhase.RUNNING)
        self.event_bus.publish(
            "haoe.lifecycle",
            lifecycle_event("started", cores=self.topology.cpu_count()).to_dict(),
        )

    def shutdown(self, timeout: float = 2.0) -> None:
        if self._state.phase in (RuntimePhase.STOPPED, RuntimePhase.CREATED):
            return
        try:
            if self._state.phase is RuntimePhase.RUNNING:
                self._state.transition(RuntimePhase.DRAINING)
            self.pools.stop_all(timeout=timeout)
            self.dispatcher._tasks.shutdown()
            self._export_performix()
            if self._state.phase is not RuntimePhase.STOPPED:
                self._state.transition(RuntimePhase.STOPPED)
        except Exception:
            self._state.transition(RuntimePhase.FAILED)
            raise
        self.event_bus.publish(
            "haoe.lifecycle",
            lifecycle_event("stopped").to_dict(),
        )

    @property
    def phase(self) -> RuntimePhase:
        return self._state.phase

    # --- scheduling API ----------------------------------------------------

    def schedule(
        self,
        task: Callable[..., Any],
        priority: str = "normal",
        *args: Any,
        numa_node: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Backward-compatible HAOEScheduler.schedule() entry point."""
        pri = _parse_priority(priority)
        if numa_node is not None:
            self.last_numa_node = int(numa_node)

        def _fn(*_a: Any, **_k: Any) -> Any:
            return task(*args, **kwargs)

        start = monotonic()
        with self.profiler.span("schedule"):
            result = self.workflow_scheduler.submit_callable(
                _fn,
                priority=pri,
                numa_node=numa_node,
                name=getattr(task, "__name__", "scheduled_task"),
            )
        elapsed = (monotonic() - start) * 1000.0
        self.metrics.inc("haoe_tasks_total")
        self.metrics.inc("haoe_workflows_total")
        self.metrics.set("haoe_task_latency_ms", elapsed)
        self.metrics.set("haoe_workflow_latency_ms", elapsed)
        self.metrics.set("haoe_queue_depth", float(self.scheduler.depth()))
        self.metrics.set("haoe_steal_total", float(self.stealer.steal_count))
        return result

    def submit_workflow(
        self,
        name: str,
        handlers: Mapping[str, Callable[[ExecutionContext], Any]],
        *,
        ids: CorrelationIds | None = None,
        context: dict[str, Any] | None = None,
        numa_node: int | None = None,
    ) -> WorkflowResult:
        if numa_node is not None:
            self.last_numa_node = int(numa_node)
        start = monotonic()
        with self.profiler.span(f"workflow:{name}"):
            if name == "chat":
                result = self.workflow_scheduler.submit_chat(
                    handlers, ids=ids, context=context, numa_node=numa_node
                )
            elif name in {"multi_agent", "swarm"}:
                result = self.workflow_scheduler.submit_multi_agent(
                    handlers, ids=ids, context=context
                )
            else:
                raise ValueError(f"unknown workflow template: {name}")
        elapsed = (monotonic() - start) * 1000.0
        self.metrics.inc("haoe_workflows_total")
        self.metrics.set("haoe_workflow_latency_ms", elapsed)
        if result.failed:
            self.metrics.inc("haoe_tasks_failed_total")
        if result.cancelled:
            self.metrics.inc("haoe_tasks_cancelled_total")
        util = self.balancer.snapshot().get("utilization", {})
        if isinstance(util, dict) and util:
            avg = sum(float(v) for v in util.values()) / max(1, len(util))
            self.metrics.set("haoe_worker_utilization", avg)
        self.metrics.set("haoe_queue_depth", float(self.scheduler.depth()))
        self._export_performix()
        return result

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "cpu_count": self.topology.cpu_count(),
            "fast_cores": list(self.fast_cores),
            "slow_cores": list(self.slow_cores),
            "features": {k: v.value for k, v in self.topology.features().items()},
            "queues": self.balancer.queue_depths(),
            "utilization": self.pools.utilization(),
            "steals": self.stealer.steal_count,
            "affinity_efficiency": self.affinity.efficiency,
            "last_numa_node": self.last_numa_node,
        }

    def _export_performix(self) -> None:
        self.performix.write_snapshot(
            {
                "status": self.status(),
                "profiler": self.profiler.summary(),
                "metrics": self.metrics.local.snapshot(),
            }
        )


def _parse_priority(value: str | PriorityClass) -> PriorityClass:
    if isinstance(value, PriorityClass):
        return value
    mapping = {
        "critical": PriorityClass.CRITICAL,
        "high": PriorityClass.HIGH,
        "normal": PriorityClass.NORMAL,
        "background": PriorityClass.BACKGROUND,
    }
    return mapping.get(str(value).lower(), PriorityClass.NORMAL)


# Alias used by router facade / docs
HAOEScheduler = HAOERuntime
