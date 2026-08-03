"""Speculative Tool Calling (Nichols et al. 2025) — Layer 2 building blocks."""

from __future__ import annotations

from .engine import SpeculativeEngine, generate_with_tool_speculation
from .executor import SpeculativeExecutor, SpeculativeTask
from .predictor import ToolCallPredictor, ToolPrediction
from .tool_cache import ToolOutputCache

__all__ = [
    "SpeculativeEngine",
    "SpeculativeExecutor",
    "SpeculativeTask",
    "ToolCallPredictor",
    "ToolOutputCache",
    "ToolPrediction",
    "generate_with_tool_speculation",
]
