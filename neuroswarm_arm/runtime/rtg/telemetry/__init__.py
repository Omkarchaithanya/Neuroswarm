"""RTG telemetry — metrics, OTEL, ARM hardware monitor."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from ..models import Decision, SessionState


class MetricsCollector:
    """Prometheus-friendly counters/gauges; optional bridge to gateway MetricsStore."""

    def __init__(self, bridge: Any | None = None) -> None:
        self.bridge = bridge
        self.counters: dict[str, float] = {}
        self.gauges: dict[str, float] = {}

    def _inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] = self.counters.get(name, 0.0) + value
        if self.bridge is not None and hasattr(self.bridge, "inc"):
            try:
                self.bridge.inc(name, value)
            except TypeError:
                self.bridge.inc(name)
        elif self.bridge is not None and hasattr(self.bridge, "set"):
            self.bridge.set(name, self.counters[name])

    def _set(self, name: str, value: float) -> None:
        self.gauges[name] = float(value)
        if self.bridge is not None and hasattr(self.bridge, "set"):
            self.bridge.set(name, float(value))

    def on_admit(self, budget: int) -> None:
        self._inc("rtg_admits_total")
        self._set("rtg_last_initial_budget", float(budget))
        self._set("neuroswarm_last_thinking_token_cap", float(budget))

    def on_decision(self, decision: Decision, state: SessionState) -> None:
        self._inc("rtg_decisions_total")
        self._inc(f"rtg_action_{decision.action.value.lower()}_total")
        if decision.terminal or decision.force_close:
            self._inc("rtg_early_exit_total")
        self._set("rtg_budget_remaining", float(state.budget.remaining_tokens))
        self._set("rtg_thinking_tokens", float(state.frame.thinking_tokens_so_far))
        self._set("rtg_last_confidence", float(state.frame.confidence_ema or state.frame.model_confidence))

    def on_complete(self, state: SessionState) -> None:
        self._inc("rtg_completions_total")
        self._set("rtg_last_session_tokens", float(state.frame.thinking_tokens_so_far))

    def render_prometheus(self) -> str:
        lines: list[str] = []
        for k, v in sorted(self.counters.items()):
            lines.append(f"# TYPE {k} counter")
            lines.append(f"{k} {v}")
        for k, v in sorted(self.gauges.items()):
            lines.append(f"# TYPE {k} gauge")
            lines.append(f"{k} {v}")
        return "\n".join(lines) + ("\n" if lines else "")


class OpenTelemetryAdapter:
    def __init__(self, *, enabled: bool = False, endpoint: str = "") -> None:
        self.enabled = enabled
        self.endpoint = endpoint

    def span(self, name: str, **attrs: Any) -> Any:
        return _NullSpan(name, attrs)


class _NullSpan:
    def __init__(self, name: str, attrs: Mapping[str, Any]) -> None:
        self.name = name
        self.attrs = dict(attrs)

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class HardwareMonitor:
    """Best-effort Arm PMU + Performix snapshot reader (Axion-safe)."""

    def __init__(
        self,
        *,
        pmu: Any | None = None,
        performix_path: str | Path | None = None,
        hardware_cfg: Mapping[str, Any] | None = None,
    ) -> None:
        self.pmu = pmu
        self.performix_path = Path(
            performix_path or "work/haoe/performix_snapshot.json"
        )
        self.cfg = dict(hardware_cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))

    def sample(self) -> dict[str, float]:
        out: dict[str, float] = {
            "cpu_utilization": 0.0,
            "memory_bandwidth_gbs": 0.0,
            "l3_miss_rate": 0.0,
            "pmu_cycles": 0.0,
            "pmu_instructions": 0.0,
            "numa_node": 0.0,
        }
        if not self.enabled:
            return out
        if self.pmu is not None:
            try:
                raw = self.pmu.read() if hasattr(self.pmu, "read") else {}
                out["pmu_cycles"] = float(raw.get("cycles", raw.get("pmu_cycles", 0.0)) or 0.0)
                out["pmu_instructions"] = float(
                    raw.get("instructions", raw.get("pmu_instructions", 0.0)) or 0.0
                )
                out["cpu_utilization"] = float(raw.get("cpu_utilization", 0.0) or 0.0)
                out["l3_miss_rate"] = float(raw.get("l3_miss_rate", 0.0) or 0.0)
            except Exception:  # noqa: BLE001
                pass
        if self.performix_path.exists():
            try:
                data = json.loads(self.performix_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    out["cpu_utilization"] = float(
                        data.get("cpu_utilization", data.get("cpu", out["cpu_utilization"])) or 0.0
                    )
                    out["memory_bandwidth_gbs"] = float(
                        data.get("memory_bandwidth_gbs", data.get("mem_bw", 0.0)) or 0.0
                    )
                    out["l3_miss_rate"] = float(data.get("l3_miss_rate", out["l3_miss_rate"]) or 0.0)
            except Exception:  # noqa: BLE001
                pass
        # Lightweight host fallback
        try:
            load = time.get_clock_info("monotonic")  # touch clocks
            _ = load
            import os

            out["cpu_utilization"] = out["cpu_utilization"] or min(
                1.0, (os.getloadavg()[0] / max(1, os.cpu_count() or 1)) if hasattr(os, "getloadavg") else 0.0
            )
        except Exception:  # noqa: BLE001
            pass
        return out

    def apply_to_frame(self, frame: Any) -> Any:
        sample = self.sample()
        frame.cpu_utilization = sample["cpu_utilization"]
        frame.memory_bandwidth_gbs = sample["memory_bandwidth_gbs"]
        frame.l3_miss_rate = sample["l3_miss_rate"]
        frame.pmu_cycles = sample["pmu_cycles"]
        frame.pmu_instructions = sample["pmu_instructions"]
        frame.numa_node = int(sample.get("numa_node", 0))
        return frame
