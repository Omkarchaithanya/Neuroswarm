"""Runtime Observability Framework (ROF) — ARMORA observability OS."""

from __future__ import annotations

from .bridges.arop_provider import ROFObservationProvider
from .bridges.dipa_adapter import DIPAObservabilityAdapter
from .bridges.haoe_adapter import HAOEObservabilityAdapter
from .bridges.performix import PerformixMetricSource
from .config import ROFRuntimeConfig, load_rof_config
from .context import (
    RuntimeTraceContext,
    clear_current_context,
    get_current_context,
    require_context,
    set_current_context,
)
from .events import EventBus
from .instrumentation import (
    bind_envelope,
    bridge_haoe_ids,
    instrument_gateway_chat,
    instrument_infer,
    instrument_planner,
    instrument_routing,
    instrument_stage,
    instrument_streaming,
)
from .middleware import ROFMiddleware, install_rof_middleware
from .plugins import (
    discover_plugins,
    register_dashboard_provider,
    register_event_type,
    register_exporter,
    register_log_sink,
    register_metric_source,
    register_sampler,
    register_trace_processor,
)
from .runtime import RuntimeObservabilityFramework, build_rof, get_rof
from .schemas import AttributeKeys, EventSeverity, EventType, SpanNames
from .spans import SpanHelper, decision_attributes

__all__ = [
    "AttributeKeys",
    "DIPAObservabilityAdapter",
    "EventBus",
    "EventSeverity",
    "EventType",
    "HAOEObservabilityAdapter",
    "PerformixMetricSource",
    "ROFMiddleware",
    "ROFObservationProvider",
    "ROFRuntimeConfig",
    "RuntimeObservabilityFramework",
    "RuntimeTraceContext",
    "SpanHelper",
    "SpanNames",
    "bind_envelope",
    "bridge_haoe_ids",
    "build_rof",
    "get_rof",
    "clear_current_context",
    "decision_attributes",
    "discover_plugins",
    "get_current_context",
    "install_rof_middleware",
    "instrument_gateway_chat",
    "instrument_infer",
    "instrument_planner",
    "instrument_routing",
    "instrument_stage",
    "instrument_streaming",
    "load_rof_config",
    "register_dashboard_provider",
    "register_event_type",
    "register_exporter",
    "register_log_sink",
    "register_metric_source",
    "register_sampler",
    "register_trace_processor",
    "require_context",
    "set_current_context",
]
