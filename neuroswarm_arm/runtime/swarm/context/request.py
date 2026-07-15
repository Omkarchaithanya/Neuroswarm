"""RequestContext — original user request surface (no execution logic)."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .models import _Base


class AttachmentRef(_Base):
    """Reference to an uploaded file / attachment."""

    name: str = ""
    mime_type: str = ""
    uri: str = ""
    size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("size_bytes")
    @classmethod
    def _non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("size_bytes must be >= 0")
        return v


class ConversationTurn(_Base):
    role: str = "user"
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RequestContext(_Base):
    """Original prompt, conversation, files, parameters, priority, policies."""

    prompt: str = ""
    conversation: list[ConversationTurn] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    attachments: list[AttachmentRef] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    workflow: str = ""
    policies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("priority")
    @classmethod
    def _priority_ok(cls, v: int) -> int:
        if v < 0:
            raise ValueError("priority must be >= 0")
        return v

    def is_empty(self) -> bool:
        return not self.prompt and not self.conversation and not self.files

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
