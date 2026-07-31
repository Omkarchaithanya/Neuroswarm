"""ASCR cost model — skip speculation when ROI / latency budget is poor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from neuroswarm_arm.runtime.dipa.interfaces.types import WorkloadClass


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class CostSignals:
    historical_acceptance: float = 0.7
    latency_used_ms: float = 0.0
    latency_budget_ms: float = 4000.0
    max_tokens: int = 1024
    workload: Any = WorkloadClass.TOOL_CALLING


def cost_model_enabled(config: dict[str, Any] | None = None) -> bool:
    """Master gate: strategies.cost_model.enabled + NSA_ASCR_COST_MODEL_ENABLED."""
    cfg = dict(config or {})
    strategies = dict(cfg.get("strategies") or {})
    body = dict(strategies.get("cost_model") or {})
    enabled = bool(body.get("enabled", False))
    if os.getenv("NSA_ASCR_COST_MODEL_ENABLED") is not None:
        enabled = _env_bool("NSA_ASCR_COST_MODEL_ENABLED", enabled)
    return enabled


def should_skip_spec(plan: Any, signals: CostSignals) -> tuple[bool, str]:
    """Return (skip, reason). True when speculation has poor ROI or tight SLA.

    Thresholds from NSA_ASCR_SKIP_* (safe defaults match strategies.cost_model).
    """
    hist_min = _env_float("NSA_ASCR_SKIP_HISTORICAL_MIN", 0.3)
    pressure_max = _env_float("NSA_ASCR_SKIP_PRESSURE_MAX", 0.8)
    max_tokens_min = _env_int("NSA_ASCR_SKIP_MAX_TOKENS_MIN", 8)

    workload = signals.workload
    if isinstance(workload, WorkloadClass):
        is_vision = workload == WorkloadClass.VISION
    else:
        is_vision = str(getattr(workload, "value", workload)).lower() == "vision"

    if is_vision:
        return True, "vision"

    if int(signals.max_tokens) < max_tokens_min:
        return True, "short"

    if float(signals.historical_acceptance) < hist_min:
        return True, "hist"

    budget = max(float(signals.latency_budget_ms), 1.0)
    pressure = float(signals.latency_used_ms) / budget
    if pressure > pressure_max:
        return True, "pressure"

    _ = plan  # plan reserved for future plan.metadata overrides
    return False, ""
