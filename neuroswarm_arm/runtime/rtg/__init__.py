"""Reasoning Token Governor (RTG) — AIM Pillar 4 peer runtime kernel."""

from __future__ import annotations

from .config import RTGRuntimeConfig, load_rtg_config
from .factory import build_rtg
from .hooks import DIPAReasoningHook
from .kernel import RTGRuntime
from .models import (
    BudgetEnvelope,
    Decision,
    GovernorAction,
    SessionState,
    TelemetryFrame,
)

__all__ = [
    "BudgetEnvelope",
    "DIPAReasoningHook",
    "Decision",
    "GovernorAction",
    "RTGRuntime",
    "RTGRuntimeConfig",
    "SessionState",
    "TelemetryFrame",
    "build_rtg",
    "load_rtg_config",
]
