"""Degraded-mode responses when all recovery paths are exhausted."""

from __future__ import annotations

from dataclasses import dataclass

from ..interfaces.types import InferenceRequest, InferenceResponse


@dataclass
class DegradedMode:
    """Emit a short, marked degraded response without calling a backend."""

    message: str = "Inference temporarily degraded."

    def respond(self, req: InferenceRequest) -> InferenceResponse:
        text = self.message
        return InferenceResponse(
            text=text,
            model=req.model or "degraded",
            tier_used=0,
            prompt_tokens=max(0, len(req.prompt_text.split())) if req.prompt_text else 0,
            completion_tokens=max(1, len(text.split())),
            thinking_token_cap=req.thinking_token_cap or 0,
            tool_schemas_used=list(req.tool_names),
            quant="",
            backend="degraded",
            plan=None,
            metrics={
                "degraded": 1.0,
                "latency_ms": 0.0,
            },
            degraded=True,
        )
