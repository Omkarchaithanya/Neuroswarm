"""NEXUS-ARM Runtime Model Resilience Engine (RMRE).

Continuously evaluates model / backend / budget / hardware health and produces
an optimal alternative execution plan while minimizing quality degradation.

Never executes inference. Never schedules CPU threads. Never owns ARMORA planning.
"""

from __future__ import annotations

from .backend import backend_compatible, compatible_backends, with_backend
from .candidates import CandidateGenerator
from .constraints import ConstraintSolver
from .context import context_fits, suggest_context, with_context
from .engine import ResilienceEngine, build_resilience_engine
from .evaluator import ResilienceEvaluator
from .events import (
    CandidateGenerated,
    EventBus,
    FallbackTriggered,
    HealthChanged,
    PolicyMatched,
    RecoveryCompleted,
    RecoveryFailed,
    ResilienceEvent,
)
from .exceptions import (
    CandidateError,
    ConstraintViolation,
    HealthError,
    PolicyError,
    RecoveryError,
    ResilienceError,
    SerializationError,
    ValidationError,
    VersionMismatchError,
)
from .execution import AlternativeExecutionPlan, ExecutionSnapshot
from .fallback import (
    DEFAULT_DIMENSIONS,
    default_dimension_configs,
    enabled_dimensions,
    resolve_cascade_strategy,
)
from .health import HealthEngine
from .history import RecoveryHistory
from .interfaces import (
    IArmoraResiliencePort,
    IBenchmarkRuntimePort,
    ICheckpointManagerPort,
    IDashboardResiliencePort,
    IDipaResiliencePort,
    IEventSink,
    IExperienceStorePort,
    IHaoeResiliencePort,
    IMetricsSink,
    IPerformixResiliencePort,
    IPolicyEnginePort,
    ISwarmContextResiliencePort,
    ITaskGraphResiliencePort,
)
from .metrics import ResilienceMetrics
from .models import (
    CascadeStrategy,
    ComponentHealth,
    DecisionKind,
    FallbackCandidate,
    FallbackDimension,
    FallbackDimensionConfig,
    HealthReport,
    HealthState,
    ModelProfile,
    ModelTier,
    RecoveryRecord,
    ResilienceDecision,
    RuntimeSignals,
    ScoreWeights,
    ScoredCandidate,
    WorkloadHint,
)
from .planner import ResiliencePlanner
from .policy import PolicyEngine, ResiliencePolicy, default_policy
from .quantization import compatible_quants, quant_supported, with_quant
from .reasoning import suggest_reasoning_budget, with_reasoning
from .recovery import RecoveryOrchestrator
from .scoring import DeterministicScorer
from .serializer import ResilienceSerializer
from .threads import suggest_threads, with_threads
from .validators import ResilienceValidator
from .versioning import SCHEMA_VERSION, current_version, migrate_payload, register_migration

__version__ = "1.0.0"

__all__ = [
    # Facade
    "ResilienceEngine",
    "build_resilience_engine",
    # Core engines
    "HealthEngine",
    "PolicyEngine",
    "CandidateGenerator",
    "ConstraintSolver",
    "DeterministicScorer",
    "ResilienceEvaluator",
    "ResiliencePlanner",
    "RecoveryOrchestrator",
    "RecoveryHistory",
    # Models
    "ModelProfile",
    "ModelTier",
    "HealthState",
    "HealthReport",
    "ComponentHealth",
    "FallbackDimension",
    "FallbackDimensionConfig",
    "CascadeStrategy",
    "DecisionKind",
    "WorkloadHint",
    "RuntimeSignals",
    "FallbackCandidate",
    "ScoredCandidate",
    "ScoreWeights",
    "RecoveryRecord",
    "ResilienceDecision",
    "ExecutionSnapshot",
    "AlternativeExecutionPlan",
    "ResiliencePolicy",
    "default_policy",
    # Dimensions
    "DEFAULT_DIMENSIONS",
    "default_dimension_configs",
    "enabled_dimensions",
    "resolve_cascade_strategy",
    "compatible_backends",
    "backend_compatible",
    "with_backend",
    "compatible_quants",
    "quant_supported",
    "with_quant",
    "context_fits",
    "suggest_context",
    "with_context",
    "suggest_reasoning_budget",
    "with_reasoning",
    "suggest_threads",
    "with_threads",
    # Events / metrics
    "EventBus",
    "ResilienceEvent",
    "FallbackTriggered",
    "CandidateGenerated",
    "PolicyMatched",
    "RecoveryCompleted",
    "RecoveryFailed",
    "HealthChanged",
    "ResilienceMetrics",
    # Serde / validation / versioning
    "ResilienceSerializer",
    "ResilienceValidator",
    "SCHEMA_VERSION",
    "current_version",
    "migrate_payload",
    "register_migration",
    # Exceptions
    "ResilienceError",
    "ValidationError",
    "PolicyError",
    "ConstraintViolation",
    "HealthError",
    "SerializationError",
    "VersionMismatchError",
    "RecoveryError",
    "CandidateError",
    # Ports
    "IArmoraResiliencePort",
    "IDipaResiliencePort",
    "IHaoeResiliencePort",
    "ITaskGraphResiliencePort",
    "ISwarmContextResiliencePort",
    "IExperienceStorePort",
    "ICheckpointManagerPort",
    "IDashboardResiliencePort",
    "IPerformixResiliencePort",
    "IBenchmarkRuntimePort",
    "IPolicyEnginePort",
    "IEventSink",
    "IMetricsSink",
]
