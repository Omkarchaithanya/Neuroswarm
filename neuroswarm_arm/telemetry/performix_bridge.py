"""Performix / arm-mcp PMU bridge for KV hot-path telemetry."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

LOG = logging.getLogger("neuroswarm.telemetry.performix")

_BRIDGE: "PerformixBridge | None" = None
_BRIDGE_LOCK = threading.Lock()


class PerformixBridge:
    """Runtime arm-mcp wrapper with schema discovery and fail-soft PMU sampling."""

    def __init__(self, *, mcp_url: str = "") -> None:
        from neuroswarm_arm.evolution.performix_mcp_client import PerformixMCPClient

        self._client = PerformixMCPClient(
            mcp_url=mcp_url or os.getenv("NSA_AROP_PERFORMIX_MCP", ""),
            timeout_s=float(os.getenv("NSA_PERFORMIX_TIMEOUT_S", "30")),
        )
        self._tools: list[str] = []
        self._recipe_fields: set[str] = set()
        self._available = False
        self._discover_tools()

    def _discover_tools(self) -> None:
        try:
            tools = self._client.list_tools()
            if isinstance(tools, list):
                self._tools = [str(t) for t in tools if t]
            self._available = "apx_recipe_run" in self._tools
            if self._available:
                self._recipe_fields = self._introspect_recipe_schema()
        except Exception as exc:
            LOG.warning("performix list_tools failed: %s", exc)
            self._available = False

    def _introspect_recipe_schema(self) -> set[str]:
        """Discover apx_recipe_run argument names at runtime (no hardcoded fields)."""
        fields: set[str] = set()
        if self._client.mcp_url.startswith("http"):
            data = self._client._http_call("tools/list", {})
            tools = data.get("tools") or data.get("result", {}).get("tools") or []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                if tool.get("name") != "apx_recipe_run":
                    continue
                schema = tool.get("inputSchema") or tool.get("input_schema") or {}
                props = schema.get("properties") or {}
                fields.update(str(k) for k in props.keys())
        if not fields:
            fields = {"recipe", "output", "duration", "target", "pid"}
        return fields

    @property
    def available(self) -> bool:
        return self._available

    def sample_pmu(self, pid: int, duration_ms: int = 100) -> dict[str, float]:
        """Return counter deltas; empty dict when arm-mcp unreachable."""
        if not self._available:
            return {}
        args: dict[str, Any] = {}
        if "recipe" in self._recipe_fields:
            args["recipe"] = os.getenv("NSA_PERFORMIX_PMU_RECIPE", "cpu_microarchitecture")
        if "duration" in self._recipe_fields:
            args["duration"] = max(1, duration_ms // 1000)
        if "target" in self._recipe_fields:
            args["target"] = str(pid)
        if "pid" in self._recipe_fields:
            args["pid"] = int(pid)
        try:
            result = self._client.recipe_run(**args) if args else self._client.recipe_run(
                os.getenv("NSA_PERFORMIX_PMU_RECIPE", "cpu_microarchitecture")
            )
            return self._parse_pmu_result(result)
        except Exception as exc:
            LOG.warning("performix sample_pmu failed: %s", exc)
            return {}

    def _parse_pmu_result(self, result: dict[str, Any]) -> dict[str, float]:
        text = ""
        if isinstance(result.get("parsed"), dict):
            payload = result["parsed"]
            return {
                "gen_ai.arm.l3_miss_rate": float(payload.get("l3_miss_rate", payload.get("L3_miss_rate", 0.0)) or 0.0),
                "gen_ai.arm.sve_util_pct": float(payload.get("sve_util_pct", payload.get("sve_utilization", 0.0)) or 0.0),
                "gen_ai.arm.branch_mispredict_pct": float(
                    payload.get("branch_mispredict_pct", payload.get("branch_miss_rate", 0.0)) or 0.0
                ),
            }
        texts = result.get("texts") or []
        if texts:
            text = texts[0]
        metrics: dict[str, float] = {}
        for line in str(text).splitlines():
            lower = line.lower()
            if "l3" in lower and "miss" in lower:
                metrics["gen_ai.arm.l3_miss_rate"] = _extract_rate(line)
            if "sve" in lower and ("util" in lower or "usage" in lower):
                metrics["gen_ai.arm.sve_util_pct"] = _extract_rate(line)
            if "branch" in lower and ("mispredict" in lower or "miss" in lower):
                metrics["gen_ai.arm.branch_mispredict_pct"] = _extract_rate(line)
        return metrics

    def schedule_sample(self, *, op: str, session_id: str = "", pid: int | None = None) -> None:
        """Fire-and-forget PMU sample; must not block hot path."""
        if os.getenv("NSA_PERFORMIX_SAMPLE", "0") != "1":
            return

        def _run() -> None:
            try:
                from neuroswarm_arm.armora.telemetry.runtime import get_rof

                target_pid = pid or os.getpid()
                attrs = self.sample_pmu(target_pid, duration_ms=100)
                if not attrs:
                    attrs = {"gen_ai.arm.performix_skipped": True}
                attrs["gen_ai.arm.performix_op"] = op
                if session_id:
                    attrs["session_id"] = session_id
                rof = get_rof()
                if rof is not None and rof.config.enabled:
                    with rof.span("nexus.performix.sample", attributes=attrs):
                        pass
            except Exception as exc:
                LOG.warning("performix async sample failed: %s", exc)

        threading.Thread(target=_run, name="performix-pmu", daemon=True).start()


def _extract_rate(line: str) -> float:
    for token in line.replace("%", " ").replace(":", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return 0.0


def get_performix_bridge() -> PerformixBridge:
    global _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is None:
            _BRIDGE = PerformixBridge()
        return _BRIDGE
