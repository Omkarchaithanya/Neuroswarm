"""ARMORA Runtime Cost Intelligence System (RCIS).

Cost is an optimization signal for planner feedback — not billing.
Budget Envelope remains the admit/enforce owner; RCIS learns from execution.
"""

from __future__ import annotations

from .accounting import DefaultAccountingEngine
from .analyzer import DefaultCostAnalyzer
from .arop_provider import RCISObservationProvider
from .config import RCISRuntimeConfig, load_rcis_config
from .estimator import DefaultLiveCostEstimator, PsutilEnergySampler
from .feedback import PlannerFeedbackService
from .plugins import (
    RCISPluginRegistry,
    register_accounting,
    register_cost_model,
    register_dashboard,
    register_energy_model,
    register_predictor,
    register_storage,
    register_telemetry,
)
from .predictor import DefaultCostPredictor
from .reports import (
    ComparisonReport,
    EnergyAnalysisReport,
    KVAnalysisReport,
    ReportBuilder,
    SpeculationReport,
)
from .repositories import BackendCostRepo, ModelTierRepo, QuantCostRepo, SpecStrategyRepo
from .runtime_cost import RuntimeCostIntelligence, build_rcis, build_rcis_at
from .schemas import (
    CostPrediction,
    HardwareMetadata,
    LiveCostBreakdown,
    Objective,
    ObservedRuntimeSignals,
    PredictionErrorReport,
    RankedChoice,
    RankedChoices,
    RequestContext,
    RuntimeCostReport,
    TelemetryMetadata,
    UnitEconomics,
    WorkloadKey,
)
from .tracker import CostSession, CostTracker

__all__ = [
    "BackendCostRepo",
    "ComparisonReport",
    "CostPrediction",
    "CostSession",
    "CostTracker",
    "DefaultAccountingEngine",
    "DefaultCostAnalyzer",
    "DefaultCostPredictor",
    "DefaultLiveCostEstimator",
    "EnergyAnalysisReport",
    "HardwareMetadata",
    "KVAnalysisReport",
    "LiveCostBreakdown",
    "ModelTierRepo",
    "Objective",
    "ObservedRuntimeSignals",
    "PlannerFeedbackService",
    "PredictionErrorReport",
    "PsutilEnergySampler",
    "QuantCostRepo",
    "RCISObservationProvider",
    "RCISPluginRegistry",
    "RCISRuntimeConfig",
    "RankedChoice",
    "RankedChoices",
    "ReportBuilder",
    "RequestContext",
    "RuntimeCostIntelligence",
    "RuntimeCostReport",
    "SpecStrategyRepo",
    "SpeculationReport",
    "TelemetryMetadata",
    "UnitEconomics",
    "WorkloadKey",
    "build_rcis",
    "build_rcis_at",
    "load_rcis_config",
    "register_accounting",
    "register_cost_model",
    "register_dashboard",
    "register_energy_model",
    "register_predictor",
    "register_storage",
    "register_telemetry",
]
