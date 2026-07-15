"""MemoryContext — working / short / long-term refs (no Mem0 / OKF logic)."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .models import ContextRefKind, ExternalRef, _Base


class CompressionMeta(_Base):
    """Metadata about context compression (ACR may fill; we only carry)."""

    strategy: str = ""
    original_tokens: int = 0
    compressed_tokens: int = 0
    ratio: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("original_tokens", "compressed_tokens")
    @classmethod
    def _non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("token counts must be >= 0")
        return v


class MemoryContext(_Base):
    """Shared memory surface: scratch + references to external memory planes."""

    session_id: str | None = None
    checkpoint_id: str | None = None
    memory_pressure: float = 0.0
    tier_hint: str = ""
    keys: list[str] = Field(default_factory=list)

    working_memory: dict[str, Any] = Field(default_factory=dict)
    short_term_memory: dict[str, Any] = Field(default_factory=dict)
    scratchpad: dict[str, Any] = Field(default_factory=dict)
    temporary_variables: dict[str, Any] = Field(default_factory=dict)

    long_term_memory_ref: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.GENERIC)
    )
    mem0_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.MEM0)
    )
    okf_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.OKF)
    )
    compression: CompressionMeta = Field(default_factory=CompressionMeta)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_pressure")
    @classmethod
    def _pressure(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("memory_pressure must be in [0, 1]")
        return v

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
