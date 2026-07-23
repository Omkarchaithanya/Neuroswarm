"""DIPARuntime — Inference Runtime Kernel (Layer 2)."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Awaitable, Mapping, TypeVar

from .backends.registry import BackendRegistry
from .batching.batch_manager import BatchManager
from .cache.kv_loader import KVLoader
from .cache.kv_writer import KVWriter
from .control.backend_manager import BackendManager
from .control.benchmark_runner import BenchmarkRunner
from .control.configuration_manager import ConfigurationManager
from .control.health_service import HealthService
from .control.inference_scheduler import InferenceScheduler
from .control.kv_cache_manager import KVCacheManager
from .control.lifecycle_manager import LifecycleManager
from .control.metrics_collector import MetricsCollector
from .control.model_manager import ModelManager
from .control.request_queue import RequestQueue
from .control.streaming_engine import StreamingEngine
from .control.telemetry_exporter import TelemetryExporter
from .control.thread_affinity_manager import ThreadAffinityManager
from .control.tokenizer_manager import TokenizerManager
from .control.warmup_manager import WarmupManager
from .engine_adapter import InferenceEngineAdapter
from .execution.execution_pipeline import ExecutionPipeline
from .execution.scheduler import PhaseScheduler
from .interfaces.engine import IInferenceEngine
from .interfaces.lifecycle import LifecyclePhase
from .interfaces.reasoning import IReasoningHook, NullReasoningHook
from .interfaces.runtime import IRuntime
from .interfaces.types import InferenceRequest, InferenceResponse
from .recovery.recovery_manager import RecoveryStack
from .router.decision_engine import DecisionEngine
from .router.request_router import RequestRouter
from .routing.quant_router import QuantRouter
from .routing.topology_router import TopologyRouter
from .runtime.runtime_config import DIPARuntimeConfig
from .runtime.runtime_registry import RuntimeRegistry
from .runtime.runtime_state import KernelState, RuntimeState
from .streaming.stream_manager import StreamManager
from .telemetry.arm_pmu import ArmPMU
from .telemetry.event_bus import EventBus
from .telemetry.metrics import DIPAMetrics
from .telemetry.perf_hooks import PerfHooks
from .telemetry.profiler import Profiler
from .telemetry.tracing import OpenTelemetryAdapter
from .warm_pool.warm_manager import WarmManager

T = TypeVar("T")


class DIPARuntime(IRuntime):
    """Production DIPA kernel. Owns all inference decisions; never agent lifecycle."""

    def __init__(
        self,
        config: DIPARuntimeConfig,
        *,
        backends: BackendRegistry,
        decision_engine: DecisionEngine,
        cascade_engine: Any,
        quant_router: QuantRouter,
        topology_router: TopologyRouter,
        warm_manager: WarmManager,
        kv_loader: KVLoader,
        kv_writer: KVWriter,
        stream_manager: StreamManager,
        recovery: RecoveryStack,
        metrics: DIPAMetrics,
        scheduler: PhaseScheduler,
        batch_manager: BatchManager | None = None,
        request_router: RequestRouter | None = None,
        event_bus: EventBus | None = None,
        profiler: Profiler | None = None,
        otel: OpenTelemetryAdapter | None = None,
        pmu: ArmPMU | None = None,
        perf_hooks: PerfHooks | None = None,
        registry: RuntimeRegistry | None = None,
        reasoning_hook: IReasoningHook | None = None,
        model_manager: ModelManager | None = None,
        backend_manager: BackendManager | None = None,
        request_queue: RequestQueue | None = None,
        inference_scheduler: InferenceScheduler | None = None,
        streaming_engine: StreamingEngine | None = None,
        kv_cache_manager: KVCacheManager | None = None,
        warmup_manager: WarmupManager | None = None,
        tokenizer_manager: TokenizerManager | None = None,
        metrics_collector: MetricsCollector | None = None,
        health_service: HealthService | None = None,
        configuration_manager: ConfigurationManager | None = None,
        lifecycle_manager: LifecycleManager | None = None,
        benchmark_runner: BenchmarkRunner | None = None,
        thread_affinity_manager: ThreadAffinityManager | None = None,
        telemetry: TelemetryExporter | None = None,
        prefill_manager: Any | None = None,
        decode_manager: Any | None = None,
        kv_transfer: Any | None = None,
        chunk_planner: Any | None = None,
        chunk_executor: Any | None = None,
        batch_scheduler: Any | None = None,
        prefix_cache: Any | None = None,
    ) -> None:
        self.config = config
        self.backends = backends
        self.decision_engine = decision_engine
        self.cascade_engine = cascade_engine
        self.quant_router = quant_router
        self.topology_router = topology_router
        self.warm_manager = warm_manager
        self.kv_loader = kv_loader
        self.kv_writer = kv_writer
        self.stream_manager = stream_manager
        self.recovery = recovery
        self.metrics = metrics
        self.scheduler = scheduler
        self.batch_manager = batch_manager or BatchManager(config.batching)
        self.request_router = request_router or RequestRouter()
        self.event_bus = event_bus or EventBus()
        self.profiler = profiler or Profiler()
        self.otel = otel or OpenTelemetryAdapter(
            enabled=config.otel_enabled, endpoint=config.otel_endpoint
        )
        self.pmu = pmu or ArmPMU()
        self.perf_hooks = perf_hooks or PerfHooks()
        self.registry = registry or RuntimeRegistry()
        self.reasoning_hook: IReasoningHook = reasoning_hook or NullReasoningHook()
        self.state = RuntimeState()
        self.pipeline = ExecutionPipeline(self)
        self.warm_manager._runner = self  # noqa: SLF001

        self.model_manager = model_manager or ModelManager()
        self.backend_manager = backend_manager or BackendManager(backends)
        self.request_queue = request_queue or RequestQueue()
        self.inference_scheduler = inference_scheduler or InferenceScheduler(
            self.request_queue
        )
        self.streaming_engine = streaming_engine or StreamingEngine()
        self.kv_cache_manager = kv_cache_manager or KVCacheManager()
        if not self.kv_cache_manager.is_wired:
            loader_conn = getattr(kv_loader, "connector", None)
            maks_conn = getattr(loader_conn, "connector", None)
            if maks_conn is not None:
                self.kv_cache_manager.attach(maks_conn)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.configuration_manager = configuration_manager or ConfigurationManager(
            config
        )
        self.lifecycle_manager = lifecycle_manager or LifecycleManager()
        self.benchmark_runner = benchmark_runner or BenchmarkRunner()
        self.thread_affinity_manager = (
            thread_affinity_manager or ThreadAffinityManager()
        )
        self.telemetry = telemetry or TelemetryExporter(
            enabled=config.otel_enabled,
            endpoint=config.otel_endpoint,
            metrics=self.metrics_collector,
        )
        self.tokenizer_manager = tokenizer_manager or TokenizerManager(
            self.backend_manager
        )
        self.warmup_manager = warmup_manager or WarmupManager(
            self.backend_manager, self.model_manager
        )
        self.health_service = health_service or HealthService(
            self.backend_manager, self.lifecycle_manager, self.metrics_collector
        )
        self.prefill_manager = prefill_manager
        self.decode_manager = decode_manager
        self.kv_transfer = kv_transfer
        self.chunk_planner = chunk_planner
        self.chunk_executor = chunk_executor
        self.batch_scheduler = batch_scheduler
        self.prefix_cache = prefix_cache
        self._engine: IInferenceEngine | None = None

    @property
    def engine(self) -> IInferenceEngine:
        if self._engine is None:
            self._engine = InferenceEngineAdapter(self)
        return self._engine

    def start(self) -> None:
        self.state.set(KernelState.STARTING)
        self.scheduler.start()
        if self.lifecycle_manager.phase().value == "created":
            try:
                self.lifecycle_manager.start()
            except Exception:
                self.lifecycle_manager.set_phase(LifecyclePhase.READY)
        self.backend_manager.start()
        self.state.set(KernelState.RUNNING)
        self.event_bus.publish("dipa.lifecycle", {"event": "start"})

    def shutdown(self) -> None:
        self.state.set(KernelState.STOPPING)
        try:
            self.lifecycle_manager.stop()
        except Exception:
            pass
        self.backend_manager.stop()
        self.scheduler.shutdown(wait=True)
        self.state.set(KernelState.STOPPED)
        self.event_bus.publish("dipa.lifecycle", {"event": "shutdown"})

    def infer(self, req: InferenceRequest | Any) -> InferenceResponse:
        normalized = self.request_router.normalize(req)
        self.event_bus.publish(
            "dipa.request",
            {
                "session_id": normalized.session_id,
                "agent_role": normalized.agent_role,
                "prompt_length": normalized.prompt_length,
            },
        )
        self.metrics_collector.incr("dipa.infer")
        with self.telemetry.span(
            "dipa.infer",
            session_id=normalized.session_id,
            agent_role=normalized.agent_role,
        ):
            with self.otel.span(
                "dipa.infer",
                session_id=normalized.session_id,
                agent_role=normalized.agent_role,
            ):
                return self.pipeline.run(normalized)

    def handle(
        self,
        req: Any,
        tool_names: list[str] | None = None,
        *,
        tool_schemas: list[dict] | None = None,
        tool_confidence: float | None = None,
        tool_prompt_block: str | None = None,
    ) -> Any:
        """HAOE / CascadeRouter-compatible entry (returns ChatResponse-shaped)."""
        from neuroswarm_arm.schemas import (
            ChatChoice,
            ChatResponse,
            ChatUsage,
            Message,
        )

        normalized = self.request_router.normalize(req)
        if tool_names:
            normalized.tool_names = list(tool_names)
        if tool_schemas is not None:
            normalized.tool_schemas = list(tool_schemas)
        if tool_confidence is not None:
            normalized.tool_confidence = float(tool_confidence)
        if tool_prompt_block:
            normalized.tool_prompt_block = tool_prompt_block
        if hasattr(req, "agent_role"):
            normalized.agent_role = getattr(req, "agent_role") or normalized.agent_role

        result = self.infer(normalized)
        return ChatResponse(
            model=getattr(req, "model", None) or result.model or "cascade",
            tier_used=result.tier_used,
            content=result.text,
            choices=[
                ChatChoice(message=Message(role="assistant", content=result.text))
            ],
            usage=ChatUsage(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.prompt_tokens + result.completion_tokens,
            ),
            tool_schemas_used=list(result.tool_schemas_used),
            thinking_token_cap=result.thinking_token_cap,
            metrics=dict(result.metrics),
        )

    def status(self) -> Mapping[str, Any]:
        out: dict[str, Any] = {
            "kernel": self.state.snapshot(),
            "backends": self.backends.list(),
            "scheduler": self.scheduler.status(),
            "metrics": self.metrics.snapshot(),
            "pmu": self.pmu.status(),
            "lifecycle": self.lifecycle_manager.snapshot(),
            "control_metrics": self.metrics_collector.snapshot(),
            "models": self.model_manager.snapshot(),
            "pd_mode": getattr(self.config, "pd_mode", "off"),
        }
        if self.prefix_cache is not None:
            out["prefix_cache"] = dict(self.prefix_cache.snapshot())
        if self.batch_scheduler is not None:
            out["batch"] = dict(self.batch_scheduler.snapshot())
        return out

    def health(self) -> Mapping[str, Any]:
        return self.health_service.health()

    def _run_async(self, coro: Awaitable[T]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()


# Public alias used in architecture docs (ADR-0006).
RuntimeManager = DIPARuntime
