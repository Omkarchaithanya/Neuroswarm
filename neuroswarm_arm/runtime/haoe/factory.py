"""DI factory for HAOE — mirrors runtime/kv/factory.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .core.dispatcher import Dispatcher
from .core.workflow_scheduler import WorkflowScheduler
from .execution.task_executor import TaskExecutor
from .interfaces.types import PoolKind
from .kernel import HAOERuntime
from .providers import (
    CallableKVPressureProvider,
    ConfigSchedulingProvider,
    SystemCPUProvider,
    SystemMemoryProvider,
    build_affinity_provider,
)
from .runtime.runtime_config import HAOERuntimeConfig, load_haoe_config
from .runtime.runtime_registry import RuntimeRegistry
from .scheduling.load_balancer import LoadBalancer
from .scheduling.priority_scheduler import PriorityScheduler
from .scheduling.queue_manager import QueueManager
from .scheduling.resource_allocator import ResourceAllocator
from .scheduling.task_cost_estimator import TaskCostEstimator
from .scheduling.work_stealing import WorkStealingScheduler
from .scheduling.worker_pool import WorkerPoolManager
from .telemetry.event_bus import EventBus
from .telemetry.metrics import HAOEMetrics
from .telemetry.opentelemetry import OpenTelemetryAdapter
from .telemetry.performix_adapter import PerformixAdapter
from .telemetry.profiler import Profiler
from .topology.affinity_manager import AffinityManager
from .topology.hardware_detector import HardwareDetector
from .topology.numa_adapter import NumaAdapter
from .topology.thread_pinning import ThreadPinning
from .topology.topology_service import TopologyService
from .workflow.cancellation import CancellationManager
from .workflow.checkpointing import CheckpointStore
from .workflow.planner import WorkflowPlanner
from .workflow.retry_manager import RetryManager
from .workflow.workflow_executor import WorkflowExecutor


def build_haoe(
    cfg: HAOERuntimeConfig | None = None,
    *,
    root: Path | None = None,
    metrics_bridge: Any | None = None,
    kv_pressure: Callable[[], Any] | Any | None = None,
    topology_cores: list[int] | None = None,
    fast_cores: list[int] | None = None,
    slow_cores: list[int] | None = None,
    start: bool = True,
) -> HAOERuntime:
    """Construct a fully wired HAOERuntime (zero global kernel state)."""
    config = cfg or load_haoe_config(root)

    # Topology / HAL
    detector_kw: dict[str, Any] = {"fast_core_fraction": config.fast_core_fraction}
    if topology_cores is not None:
        detector_kw["override_cores"] = list(topology_cores)
    elif fast_cores or slow_cores:
        detector_kw["override_cores"] = list(fast_cores or []) + list(slow_cores or [])

    snapshot = HardwareDetector(**detector_kw).detect()
    if fast_cores is not None:
        snapshot.topology.fast_cores = list(fast_cores)
    if slow_cores is not None:
        snapshot.topology.efficiency_cores = list(slow_cores)

    topology = TopologyService(snapshot)
    affinity_provider = build_affinity_provider(enabled=config.affinity_enabled)
    pinning = ThreadPinning(affinity_provider, enabled=config.affinity_enabled)
    numa = NumaAdapter(topology)
    affinity = AffinityManager(
        topology, pinning, numa, enabled=config.affinity_enabled
    )

    # Scheduling
    queues = QueueManager()
    stealer = WorkStealingScheduler(queues, attempts=config.steal_attempts)
    priority = PriorityScheduler(
        queues,
        stealer,
        aging_enabled=config.priority_aging,
        aging_step=config.aging_step,
    )
    kv_provider = CallableKVPressureProvider(kv_pressure)
    memory = SystemMemoryProvider()
    estimator = TaskCostEstimator(kv=kv_provider, memory_pressure_fn=memory.pressure)
    # Temporary balancer without pools; rebind after pools created
    balancer = LoadBalancer(queues, pools=None)
    allocator = ResourceAllocator(estimator, balancer, affinity)

    # Execution / workflow
    event_bus = EventBus()
    metrics = HAOEMetrics(bridge=metrics_bridge)
    profiler = Profiler()
    performix = PerformixAdapter(config.performix_snapshot_path)
    otel = OpenTelemetryAdapter(
        enabled=config.otel_enabled, endpoint=config.otel_endpoint
    )
    retry = RetryManager()
    task_executor = TaskExecutor(
        thread_workers=config.thread_pool_workers,
        process_workers=config.process_pool_workers,
        retry_manager=retry,
    )
    checkpoints = CheckpointStore(config.checkpoint_dir)  # type: ignore[arg-type]
    cancellations = CancellationManager()
    workflow_executor = WorkflowExecutor(
        task_executor,
        checkpoints=checkpoints,
        cancellations=cancellations,
        event_bus=event_bus,
        retry_manager=retry,
    )
    dispatcher = Dispatcher(priority, allocator, task_executor, workflow_executor)
    planner = WorkflowPlanner()
    workflow_scheduler = WorkflowScheduler(planner, dispatcher)

    sizes = {kind: config.pool_size(kind) for kind in PoolKind}
    pools = WorkerPoolManager(
        priority,
        queues,
        sizes,
        on_task=dispatcher.handle_queued_task,
        affinity=affinity,
    )
    balancer._pools = pools  # noqa: SLF001 — late bind after construction

    registry = RuntimeRegistry()
    registry.register("topology", topology)
    registry.register("affinity", affinity)
    registry.register("cpu", SystemCPUProvider(topology))
    registry.register("memory", memory)
    registry.register("kv_pressure", kv_provider)
    registry.register("scheduling", ConfigSchedulingProvider(config))
    registry.register("otel", otel)
    registry.register("event_bus", event_bus)
    registry.register("metrics", metrics)

    runtime = HAOERuntime(
        config,
        topology=topology,
        affinity=affinity,
        queues=queues,
        stealer=stealer,
        scheduler=priority,
        pools=pools,
        balancer=balancer,
        dispatcher=dispatcher,
        workflow_scheduler=workflow_scheduler,
        planner=planner,
        event_bus=event_bus,
        metrics=metrics,
        profiler=profiler,
        performix=performix,
        registry=registry,
        fast_cores=snapshot.topology.fast_cores,
        slow_cores=snapshot.topology.efficiency_cores,
    )
    if start:
        runtime.start()
    return runtime
