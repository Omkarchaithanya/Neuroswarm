"""Tool validation."""

from __future__ import annotations

from .models import ToolRecord
from .router_exceptions import ToolValidationError


def validate_tool_record(tool: ToolRecord) -> None:
    if not tool.id or not str(tool.id).strip():
        raise ToolValidationError("tool.id required")
    if not tool.name or not str(tool.name).strip():
        raise ToolValidationError("tool.name required")
    if tool.cost_usd < 0:
        raise ToolValidationError("tool.cost_usd must be >= 0")
    if tool.p50_latency_ms < 0:
        raise ToolValidationError("tool.p50_latency_ms must be >= 0")
    if not (0.0 <= tool.success_rate <= 1.0):
        raise ToolValidationError("tool.success_rate must be in [0,1]")
    if not (0.0 <= tool.failure_rate <= 1.0):
        raise ToolValidationError("tool.failure_rate must be in [0,1]")
