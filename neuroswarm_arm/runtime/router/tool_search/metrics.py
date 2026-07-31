"""tool_search metrics via existing RouterMetrics."""

from __future__ import annotations

from typing import Any, Literal

from ..router_metrics import RouterMetrics

ModeName = Literal["bridge", "pass_through"]

_METRICS: RouterMetrics | None = None


def get_tool_search_metrics(bridge: Any | None = None) -> RouterMetrics:
    global _METRICS
    if _METRICS is None:
        _METRICS = RouterMetrics(bridge=bridge)
        # Ensure defs present even if RouterMetrics constructed elsewhere first.
        _METRICS.local.setdefault("tool_search_mode_total_bridge", 0.0)
        _METRICS.local.setdefault("tool_search_mode_total_pass_through", 0.0)
        _METRICS.local.setdefault("tool_search_truncated_total", 0.0)
    return _METRICS


def record_mode(mode: ModeName, metrics: RouterMetrics | None = None) -> None:
    m = metrics or get_tool_search_metrics()
    if mode == "bridge":
        m.inc("tool_search_mode_total_bridge")
        m.inc("tool_search_mode_total", 1.0)  # unlabeled rollup
    else:
        m.inc("tool_search_mode_total_pass_through")
        m.inc("tool_search_mode_total", 1.0)


def record_truncated(metrics: RouterMetrics | None = None) -> None:
    m = metrics or get_tool_search_metrics()
    m.inc("tool_search_truncated_total")
