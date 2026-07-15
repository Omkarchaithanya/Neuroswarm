"""Artifact references — handles only, never binary payloads."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .models import ArtifactKind, _Frozen


class ArtifactRef(_Frozen):
    """Immutable reference to an external artifact blob."""

    artifact_id: str
    kind: ArtifactKind
    uri: str
    media_type: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("uri")
    @classmethod
    def _uri_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("uri must be non-empty")
        return v.strip()

    @field_validator("size_bytes")
    @classmethod
    def _size_ok(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("size_bytes must be >= 0")
        return v
