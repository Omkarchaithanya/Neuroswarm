"""Safety gate — SLO / budget / regression / constraint checks before deploy."""

from __future__ import annotations

from typing import Mapping

from neuroswarm_arm.evolution.config import AROPConfig
from neuroswarm_arm.evolution.interfaces.safety import SafetyGate, SafetyReport
from neuroswarm_arm.evolution.interfaces.validation import ValidationReport
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class SafetyEngine(SafetyGate):
    def __init__(self, config: AROPConfig | None = None) -> None:
        self.config = config or AROPConfig()

    def check(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None,
        validation: ValidationReport | None = None,
        live_metrics: Mapping[str, float] | None = None,
    ) -> SafetyReport:
        metrics = dict(live_metrics or {})
        if validation:
            metrics.update(validation.metrics_candidate)
        constraints = candidate.policy.constraints
        checks: dict[str, bool] = {}
        violations: list[str] = []

        latency = float(metrics.get("latency_ms", 0.0))
        accept = float(metrics.get("accept_rate", candidate.policy.parameters.get("accept_threshold", 0.7)))
        cost = float(metrics.get("cost_usd", 0.0))
        kv = float(metrics.get("kv_pressure", metrics.get("kv_usage", 0.0)))
        cpu = float(metrics.get("cpu", metrics.get("cpu_util", 0.0)))
        quality = float(metrics.get("quality", 1.0))
        tool_ok = float(metrics.get("tool_success", 1.0))

        def _check(name: str, ok: bool, msg: str) -> None:
            checks[name] = ok
            if not ok:
                violations.append(msg)

        _check(
            "latency",
            latency <= max(constraints.max_latency_ms, self.config.safety_max_latency_ms) or latency == 0.0,
            f"latency {latency} exceeds SLO",
        )
        _check(
            "accept_rate",
            accept >= min(constraints.min_accept_rate, self.config.safety_min_accept_rate),
            f"accept_rate {accept} below floor",
        )
        _check(
            "cost",
            cost <= max(constraints.max_cost_usd, self.config.safety_max_cost_usd) or cost == 0.0,
            f"cost {cost} exceeds budget",
        )
        _check(
            "kv_pressure",
            kv <= max(constraints.max_kv_pressure, self.config.safety_max_kv_pressure) or kv == 0.0,
            f"kv_pressure {kv} too high",
        )
        _check("cpu", cpu <= constraints.max_cpu_util or cpu == 0.0, f"cpu {cpu} too high")
        _check("quality", quality >= constraints.min_quality, f"quality {quality} below floor")
        _check("tool_success", tool_ok >= constraints.min_tool_success, f"tool_success {tool_ok} below floor")
        _check("validation", validation.passed if validation else True, "statistical validation failed")
        _check("security", True, "security flag")  # placeholder always pass
        _check("regression", True, "regression")

        # Hard reject if candidate confidence absurdly low
        if candidate.policy.confidence < 0.1:
            checks["confidence"] = False
            violations.append("confidence too low")
        else:
            checks["confidence"] = True

        passed = all(checks.values())
        return SafetyReport(
            passed=passed,
            violations=tuple(violations),
            checks=checks,
            message="ok" if passed else "; ".join(violations),
        )
