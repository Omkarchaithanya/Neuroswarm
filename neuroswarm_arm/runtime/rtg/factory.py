"""DI factory for RTG — mirrors HAOE/DIPA/MAKS factories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import RTGRuntimeConfig, load_rtg_config
from .control import (
    BudgetAllocator,
    DecisionEngine,
    EarlyExitEngine,
    RuntimeController,
    StreamingController,
    SwarmBudgetManager,
)
from .estimators import AnswerStabilityEstimator, BudgetPredictor, ReasoningROIEstimator
from .events import EventBus
from .kernel import RTGRuntime
from .policy import PolicyEngine
from .sensors import (
    ComplexityEstimator,
    ConfidenceEstimator,
    EntropyMonitor,
    KVPressureSensor,
    LatencySLOSensor,
    PlateauDetector,
    SelfConsistencyMonitor,
    SemanticSensor,
)
from .telemetry import HardwareMonitor, MetricsCollector, OpenTelemetryAdapter


def build_rtg(
    cfg: RTGRuntimeConfig | None = None,
    *,
    root: Path | None = None,
    metrics_bridge: Any | None = None,
    kv_pressure: Any | None = None,
    semantic_router: Any | None = None,
    pmu: Any | None = None,
    performix_path: str | Path | None = None,
) -> RTGRuntime:
    config = cfg or load_rtg_config(root)
    events = EventBus()
    metrics = MetricsCollector(bridge=metrics_bridge)
    otel = OpenTelemetryAdapter(enabled=config.otel_enabled, endpoint=config.otel_endpoint)
    hardware = HardwareMonitor(
        pmu=pmu,
        performix_path=performix_path or config.hardware.get("performix_snapshot"),
        hardware_cfg=config.hardware,
    )
    predictor = BudgetPredictor(config)
    allocator = BudgetAllocator(config, predictor)
    policy = PolicyEngine(config)
    decision_engine = DecisionEngine(policy)
    swarm = SwarmBudgetManager(config)
    controller = RuntimeController()
    early_exit = EarlyExitEngine()
    sensors = [
        ComplexityEstimator(),
        SemanticSensor(semantic_router),
        KVPressureSensor(kv_pressure),
        LatencySLOSensor(default_slo_ms=config.slo_soft_ms),
        EntropyMonitor(),
        ConfidenceEstimator(),
        SelfConsistencyMonitor(),
        PlateauDetector(epsilon=config.plateau_epsilon, windows=config.plateau_windows),
    ]
    estimators = [
        ReasoningROIEstimator(config),
        AnswerStabilityEstimator(),
    ]
    streaming = StreamingController(
        config,
        allocator=allocator,
        decision_engine=decision_engine,
        sensors=sensors,
        estimators=estimators,
        swarm=swarm,
        events=events,
        metrics=metrics,
        early_exit=early_exit,
        controller=controller,
    )
    return RTGRuntime(
        config,
        streaming=streaming,
        allocator=allocator,
        policy=policy,
        metrics=metrics,
        events=events,
        hardware=hardware,
        otel=otel,
        swarm=swarm,
        controller=controller,
        early_exit=early_exit,
    )
