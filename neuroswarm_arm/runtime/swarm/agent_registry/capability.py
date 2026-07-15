"""AgentCapability — typed capability surface for discovery and selection."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentCapability(BaseModel):
    """Declarative capability matrix for an agent."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    supported_tasks: list[str] = Field(default_factory=list)
    supported_workflows: list[str] = Field(default_factory=list)
    supported_tools: list[str] = Field(default_factory=list)
    supported_models: list[str] = Field(default_factory=list)
    supported_backends: list[str] = Field(default_factory=list)
    supported_quantizations: list[str] = Field(default_factory=list)
    supported_embeddings: list[str] = Field(default_factory=list)
    supported_memory: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    supported_file_types: list[str] = Field(default_factory=list)

    supports_streaming: bool = False
    supports_reasoning: bool = False
    supports_review: bool = False
    supports_planning: bool = False
    supports_parallel: bool = False
    supports_checkpoint: bool = False
    supports_resume: bool = False
    supports_retry: bool = True
    supports_metrics: bool = True
    supports_cost_tracking: bool = True
    supports_observability: bool = True

    max_context: int = 8192
    max_tokens: int = 4096

    preferred_models: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    preferred_quantization: str | None = None
    preferred_backend: str | None = None

    @field_validator(
        "max_context",
        "max_tokens",
    )
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v

    def capability_keys(self) -> list[str]:
        """Flatten boolean + list capabilities into indexable keys."""
        keys: list[str] = []
        for name in self.supported_tasks:
            keys.append(f"task:{name}")
        for name in self.supported_workflows:
            keys.append(f"workflow:{name}")
        for name in self.supported_tools:
            keys.append(f"tool:{name}")
        for name in self.supported_models:
            keys.append(f"model:{name}")
        for name in self.supported_backends:
            keys.append(f"backend:{name}")
        for name in self.supported_quantizations:
            keys.append(f"quant:{name}")
        flags = (
            ("streaming", self.supports_streaming),
            ("reasoning", self.supports_reasoning),
            ("review", self.supports_review),
            ("planning", self.supports_planning),
            ("parallel", self.supports_parallel),
            ("checkpoint", self.supports_checkpoint),
            ("resume", self.supports_resume),
            ("retry", self.supports_retry),
        )
        for flag, enabled in flags:
            if enabled:
                keys.append(f"flag:{flag}")
        return keys

    def overlaps(self, required: list[str], *, attr: str) -> float:
        """Jaccard-like overlap of required items vs supported list on attr."""
        supported = list(getattr(self, attr, []) or [])
        if not required:
            return 1.0
        if not supported:
            return 0.0
        req = set(required)
        sup = set(supported)
        hit = len(req & sup)
        return hit / len(req)

    def to_index_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
