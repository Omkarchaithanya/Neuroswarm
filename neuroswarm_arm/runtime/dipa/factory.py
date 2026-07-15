"""DI factory for DIPA — mirrors runtime/haoe/factory.py and runtime/kv/factory.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .aqr.quant_connector import AQRQuantConnector
from .awpp.warm_connector import HeuristicWarmConnector
from .backends.factory import BackendFactory
from .backends.registry import BackendRegistry
from .batching.batch_manager import BatchManager
from .cache.kv_connector import KVConnector
from .cache.kv_loader import KVLoader
from .cache.kv_writer import KVWriter
from .cache.maks_connector import MAKSConnector
from .cache.prefix_cache_manager import PrefixCacheManager
from .control.backend_manager import BackendManager
from .control.benchmark_runner import BenchmarkRunner
from .control.configuration_manager import ConfigurationManager
from .control.hardware_detector import ControlHardwareDetector
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
from .execution.scheduler import PhaseScheduler
from .interfaces.kv_cache import IKVCacheConnector
from .interfaces.lifecycle import LifecyclePhase
from .interfaces.quantizer import IQuantConnector
from .interfaces.reasoning import IReasoningHook, NullReasoningHook
from .interfaces.types import FeatureStatus, KVTransferMode
from .interfaces.warm import IWarmConnector
from .kernel import DIPARuntime
from .pd.batch_scheduler import BatchScheduler
from .pd.chunk_executor import ChunkExecutor
from .pd.chunk_planner import ChunkPlanner
from .pd.decode_manager import DecodeManager
from .pd.kv_transfer import KVTransferManager
from .pd.prefill_manager import PrefillManager
from .recovery.circuit_breaker import CircuitBreaker
from .recovery.recovery_manager import RecoveryStack
from .recovery.retry_manager import RetryManager
from .recovery.timeout_manager import TimeoutManager
from .router.decision_engine import DecisionEngine
from .router.execution_planner import ExecutionPlanner
from .router.policy_engine import PolicyEngine
from .router.request_router import RequestRouter
from .routing.backend_selector import BackendSelector
from .routing.model_router import ModelRouter
from .routing.quant_router import QuantRouter
from .routing.speculation_router import SpeculationRouter
from .routing.topology_router import TopologyRouter
from .runtime.runtime_config import DIPARuntimeConfig, load_dipa_config
from .runtime.runtime_registry import RuntimeRegistry
from .streaming.stream_manager import StreamManager
from .telemetry.arm_pmu import ArmPMU
from .telemetry.event_bus import EventBus
from .telemetry.metrics import DIPAMetrics
from .telemetry.perf_hooks import PerfHooks
from .telemetry.profiler import Profiler
from .telemetry.tracing import OpenTelemetryAdapter
from .topology.hardware_detector import HardwareDetector
from .warm_pool.model_pool import ModelPool
from .warm_pool.session_pool import SessionPool
from .warm_pool.warm_manager import WarmManager


def build_dipa(
    cfg: DIPARuntimeConfig | None = None,
    *,
    root: Path | None = None,
    metrics_bridge: Any | None = None,
    tier_urls: Mapping[str, str] | None = None,
    backends: BackendRegistry | None = None,
    aqr: IQuantConnector | None = None,
    awpp: IWarmConnector | None = None,
    maks: IKVCacheConnector | None = None,
    reasoning_hook: IReasoningHook | None = None,
    use_mock: bool = False,
    topology_cores: Sequence[int] | None = None,
    start: bool = True,
) -> DIPARuntime:
    """Construct a fully wired DIPARuntime (zero global kernel state)."""
    config = cfg or load_dipa_config(root)

    factory = BackendFactory(config)
    registry = factory.build_registry(
        tier_urls=tier_urls,
        use_mock=use_mock,
        existing=backends,
    )

    if aqr is None:
        try:
            from neuroswarm_arm.runtime.aqr import pick_quant_primary

            aqr = AQRQuantConnector(pick_fn=pick_quant_primary)
        except Exception:
            try:
                from neuroswarm_arm.aqr import pick_quant

                aqr = AQRQuantConnector(pick_fn=pick_quant)
            except Exception:
                aqr = AQRQuantConnector()
    warm = awpp or HeuristicWarmConnector()
    kv_conn = KVConnector(maks or MAKSConnector())
    kv_loader = KVLoader(kv_conn)
    kv_writer = KVWriter(kv_conn)
    if hasattr(warm, "bind_maks") and maks is not None:
        sharing = getattr(maks, "_sharing", None) or getattr(maks, "_manager", None)
        if sharing is not None and hasattr(sharing, "prefetch"):
            warm.bind_maks(sharing)  # type: ignore[attr-defined]
        elif hasattr(maks, "prefetch"):
            warm.bind_maks(maks)  # type: ignore[attr-defined]

    hw_cfg = dict(config.hardware)
    fraction = float(
        (hw_cfg.get("core_partition") or {}).get("prefill_fraction", 0.4)
    )
    detector = HardwareDetector(
        prefill_fraction=fraction,
        override_cores=list(topology_cores) if topology_cores else None,
    )
    snapshot = detector.detect()
    topology_router = TopologyRouter(hw_cfg, detector=snapshot)

    config_mgr = ConfigurationManager(config)
    metrics_collector = MetricsCollector()
    telemetry = TelemetryExporter(
        enabled=config.otel_enabled,
        endpoint=config.otel_endpoint,
        metrics=metrics_collector,
    )
    lifecycle = LifecycleManager()
    affinity = ThreadAffinityManager()
    hw_control = ControlHardwareDetector()
    hw_profile = hw_control.detect()
    backend_mgr = BackendManager(registry)
    model_mgr = ModelManager()
    request_queue = RequestQueue(maxsize=config_mgr.queue_maxsize())
    inference_sched = InferenceScheduler(
        request_queue, workers=config_mgr.scheduler_workers()
    )
    streaming_engine = StreamingEngine()
    kv_cache_mgr = KVCacheManager(kv_conn.connector)
    tokenizer_mgr = TokenizerManager(backend_mgr)

    metrics = DIPAMetrics(bridge=metrics_bridge)
    prefix_cache = PrefixCacheManager(
        sglang_backend=registry.get("sglang"),
        maks=kv_conn.connector,
        metrics=metrics,
    )
    warmup_mgr = WarmupManager(
        backend_mgr, model_mgr, warm=warm, prefix_cache=prefix_cache
    )
    health_svc = HealthService(
        backend_mgr,
        lifecycle,
        metrics_collector,
        config=config,
        backends_registry=registry,
    )
    bench = BenchmarkRunner()

    def _detect() -> None:
        telemetry.event("lifecycle.detect", numa=hw_profile.numa_nodes)
        metrics_collector.gauge("hardware.cpu_count", float(hw_profile.cpu_count))

    def _affinity() -> None:
        prefill_cores = list(snapshot.prefill_cores) or affinity.available_cpus()
        decode_cores = list(getattr(snapshot, "decode_cores", []) or [])
        if not decode_cores:
            all_cores = affinity.available_cpus()
            mid = max(1, len(all_cores) * 2 // 5)
            decode_cores = all_cores[mid:] or all_cores
        affinity.bind(
            "dipa-prefill", prefill_cores[: max(1, len(prefill_cores) // 2) or 1]
        )
        affinity.bind(
            "dipa-decode", decode_cores[: max(1, len(decode_cores) // 2) or 1]
        )

    def _backends() -> None:
        backend_mgr.start()

    def _models() -> None:
        for name in ("tier1", "tier2", "tier3", "sglang"):
            if registry.get(name) is not None:
                model_mgr.load(name, backend=name)

    def _warmup() -> None:
        warmup_mgr.warmup()

    lifecycle.on(LifecyclePhase.DETECTING, _detect)
    lifecycle.on(LifecyclePhase.AFFINITY, _affinity)
    lifecycle.on(LifecyclePhase.BACKENDS, _backends)
    lifecycle.on(LifecyclePhase.MODELS, _models)
    lifecycle.on(LifecyclePhase.WARMUP, _warmup)

    policy_engine = PolicyEngine(config.policy)
    planner = ExecutionPlanner(policy_engine)
    model_router = ModelRouter(config.routing)
    backend_selector = BackendSelector(registry, config.routing)
    speculation_router = SpeculationRouter(config.cascade)
    decision_engine = DecisionEngine(
        policy_engine,
        model_router,
        backend_selector,
        speculation_router,
        planner,
        config=config,
    )
    quant_router = QuantRouter(aqr)

    cascade_cfg = dict(config.cascade or {})
    if config.cascade_confidence:
        tiers = [dict(t) for t in (cascade_cfg.get("tiers") or [])]
        if tiers:
            tiers[0]["acceptance_threshold"] = float(config.cascade_confidence)
            cascade_cfg["tiers"] = tiers
        ascr_block = dict(cascade_cfg.get("ascr") or {})
        ascr_block["accept_threshold"] = float(config.cascade_confidence)
        cascade_cfg["ascr"] = ascr_block
        spec = dict(cascade_cfg.get("speculation") or {})
        spec["accept_threshold"] = float(config.cascade_confidence)
        cascade_cfg["speculation"] = spec
    # ASCR replaces heuristic CascadeEngine (ADR-0008).
    from neuroswarm_arm.runtime.armcascade.factory import build_ascr

    cascade_engine = build_ascr(
        registry,
        dipa_cascade_cfg=cascade_cfg,
        metrics_bridge=metrics,
    )

    model_pool = ModelPool()
    session_pool = SessionPool()
    warm_manager = WarmManager(
        warm, model_pool=model_pool, session_pool=session_pool
    )
    stream_manager = StreamManager.from_dict(config.streaming)
    recovery = RecoveryStack(
        registry=registry,
        retry=RetryManager(max_retries=config.max_retries),
        timeout=TimeoutManager(default_timeout_s=config.default_timeout_s),
        circuit=CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            reset_window_s=config.circuit_reset_s,
        ),
        telemetry=telemetry,
    )
    batch_manager = BatchManager(config.batching)
    batch_scheduler = BatchScheduler(batch_manager)
    scheduler = PhaseScheduler(
        prefill_workers=config.prefill_pool_size,
        decode_workers=config.decode_pool_size,
    )

    event_bus = EventBus()
    profiler = Profiler()
    otel = OpenTelemetryAdapter(exporter=telemetry)
    pmu = ArmPMU()
    perf = PerfHooks()

    kv_transfer = KVTransferManager(
        mooncake_status=FeatureStatus.UNAVAILABLE,
        nixl_status=FeatureStatus.UNAVAILABLE,
        default_mode=(
            KVTransferMode.NATIVE_SGLANG
            if config.pd_mode == "native"
            else KVTransferMode.RECOMPUTE
        ),
    )
    prefill_manager = PrefillManager(
        registry,
        default_backend=config.prefill_backend or "sglang",
        metrics=metrics,
        otel=otel,
        prefix_cache=prefix_cache,
    )
    decode_manager = DecodeManager(
        registry,
        default_backend=config.decode_backend or "llama_cpp",
        metrics=metrics,
        otel=otel,
    )
    chunk_planner = ChunkPlanner()
    chunk_executor = ChunkExecutor(prefill_manager)

    component_registry = RuntimeRegistry()
    component_registry.register("backends", registry)
    component_registry.register("topology", snapshot)
    component_registry.register("hardware_profile", hw_profile)
    component_registry.register("metrics", metrics)
    component_registry.register("event_bus", event_bus)
    component_registry.register("aqr", aqr)
    component_registry.register("awpp", warm)
    component_registry.register("maks", kv_conn.connector)
    hook = reasoning_hook or NullReasoningHook()
    component_registry.register("rtg", hook)
    component_registry.register("lifecycle", lifecycle)
    component_registry.register("telemetry", telemetry)
    component_registry.register("prefix_cache", prefix_cache)
    component_registry.register(
        "pd",
        {
            "prefill": prefill_manager,
            "decode": decode_manager,
            "transfer": kv_transfer,
        },
    )

    runtime = DIPARuntime(
        config,
        backends=registry,
        decision_engine=decision_engine,
        cascade_engine=cascade_engine,
        quant_router=quant_router,
        topology_router=topology_router,
        warm_manager=warm_manager,
        kv_loader=kv_loader,
        kv_writer=kv_writer,
        stream_manager=stream_manager,
        recovery=recovery,
        metrics=metrics,
        scheduler=scheduler,
        batch_manager=batch_manager,
        request_router=RequestRouter(),
        event_bus=event_bus,
        profiler=profiler,
        otel=otel,
        pmu=pmu,
        perf_hooks=perf,
        registry=component_registry,
        reasoning_hook=hook,
        model_manager=model_mgr,
        backend_manager=backend_mgr,
        request_queue=request_queue,
        inference_scheduler=inference_sched,
        streaming_engine=streaming_engine,
        kv_cache_manager=kv_cache_mgr,
        warmup_manager=warmup_mgr,
        tokenizer_manager=tokenizer_mgr,
        metrics_collector=metrics_collector,
        health_service=health_svc,
        configuration_manager=config_mgr,
        lifecycle_manager=lifecycle,
        benchmark_runner=bench,
        thread_affinity_manager=affinity,
        telemetry=telemetry,
        prefill_manager=prefill_manager,
        decode_manager=decode_manager,
        kv_transfer=kv_transfer,
        chunk_planner=chunk_planner,
        chunk_executor=chunk_executor,
        batch_scheduler=batch_scheduler,
        prefix_cache=prefix_cache,
    )
    if start:
        runtime.start()
    return runtime
