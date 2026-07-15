"""ARMORA Budget Envelope — unified runtime resource contract."""

from __future__ import annotations

from .accounting import ExecutionAccounting
from .compat import ArmoraBudgetPolicy, BudgetConfig
from .categories import (
    BudgetCategory,
    CompletionTokenBudget,
    ComputeBudget,
    ConcurrencyBudget,
    CostBudget,
    EnergyBudget,
    KVBudget,
    LatencyBudget,
    MemoryBudget,
    PromptTokenBudget,
    ReasoningTokenBudget,
    RetryBudget,
    StreamingBudget,
    TokenBudget,
    ToolBudget,
)
from .config import BudgetRuntimeConfig, load_budget_config
from .envelope import BudgetEnvelope, build_envelope_from_template
from .estimator import DefaultCostModel, DefaultEnergyModel, DefaultEstimator
from .lifecycle import BudgetLifecycle
from .optimizer import BudgetOptimizer, OptimizeResult
from .plugins import (
    BudgetPluginRegistry,
    register_accounting,
    register_cost_model,
    register_dimension,
    register_energy_model,
    register_estimator,
    register_persistence,
    register_policy_compiler,
    register_telemetry,
)
from .policy import DefaultPolicyCompiler, PolicyEngine
from .reports import ReportBundle, ReportBuilder
from .schemas import (
    AdmitDecision,
    AffordDecision,
    BackendPreferences,
    CancellationPolicy,
    ChargebackTags,
    DimensionDelta,
    EnvelopeTemplate,
    ExecutionSLA,
    FailurePolicy,
    Hardness,
    HardwareConstraints,
    LifecyclePhase,
    PlanAction,
    PlanActionKind,
    QualityRequirement,
    ResourceProjection,
    ViolationState,
)
from .rtg_adapter import ReasoningBudgetView
from .service import BudgetService, build_budget_service
from .tracker import BudgetRuntimeState, BudgetTracker
from .validator import BudgetValidator

__all__ = [
    "AdmitDecision",
    "AffordDecision",
    "ArmoraBudgetPolicy",
    "BackendPreferences",
    "BudgetCategory",
    "BudgetConfig",
    "BudgetEnvelope",
    "BudgetLifecycle",
    "BudgetOptimizer",
    "BudgetPluginRegistry",
    "BudgetRuntimeConfig",
    "BudgetRuntimeState",
    "BudgetService",
    "BudgetTracker",
    "BudgetValidator",
    "CancellationPolicy",
    "ChargebackTags",
    "CompletionTokenBudget",
    "ComputeBudget",
    "ConcurrencyBudget",
    "CostBudget",
    "DefaultCostModel",
    "DefaultEnergyModel",
    "DefaultEstimator",
    "DefaultPolicyCompiler",
    "DimensionDelta",
    "EnergyBudget",
    "EnvelopeTemplate",
    "ExecutionAccounting",
    "ExecutionSLA",
    "FailurePolicy",
    "Hardness",
    "HardwareConstraints",
    "KVBudget",
    "LatencyBudget",
    "LifecyclePhase",
    "MemoryBudget",
    "OptimizeResult",
    "PlanAction",
    "PlanActionKind",
    "PolicyEngine",
    "PromptTokenBudget",
    "QualityRequirement",
    "ReasoningBudgetView",
    "ReasoningTokenBudget",
    "ReportBuilder",
    "ReportBundle",
    "ResourceProjection",
    "RetryBudget",
    "StreamingBudget",
    "TokenBudget",
    "ToolBudget",
    "ViolationState",
    "build_budget_service",
    "build_envelope_from_template",
    "load_budget_config",
    "register_accounting",
    "register_cost_model",
    "register_dimension",
    "register_energy_model",
    "register_estimator",
    "register_persistence",
    "register_policy_compiler",
    "register_telemetry",
]
