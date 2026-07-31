"""Semantic MCP Tool Router — production AIM Pillar 2 service."""

from __future__ import annotations

from .cost_router import CostDecision, CostRouter
from .factory import build_router
from .models import RouteContext, RoutingResult, ScoredTool, ToolRecord
from .orchestration import RoutedInferenceHints, build_routed_inference_hints
from .router_api import create_tool_router
from .router_config import RouterConfig, load_router_config
from .tool_router import SemanticToolRouter
from .tool_search import ToolSearchConfig, decide_mode

__all__ = [
    "CostDecision",
    "CostRouter",
    "RouteContext",
    "RoutedInferenceHints",
    "RouterConfig",
    "RoutingResult",
    "ScoredTool",
    "SemanticToolRouter",
    "ToolRecord",
    "ToolSearchConfig",
    "build_routed_inference_hints",
    "build_router",
    "create_tool_router",
    "decide_mode",
    "load_router_config",
]
