"""TaskEdge — dependency between TaskNodes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import EdgeKind
from .utils import stable_hash


class TaskEdge(BaseModel):
    """Directed dependency edge with kind, label, condition, and metadata."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    src: str
    dst: str
    kind: EdgeKind = EdgeKind.HARD
    label: str = ""
    condition: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    priority_boost: int = 0
    data_key: str | None = None

    def key(self) -> tuple[str, str, str]:
        return (self.src, self.dst, self.kind.value)

    def clone(self) -> TaskEdge:
        return TaskEdge.model_validate(self.model_dump(mode="python"))

    def definition_payload(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "kind": self.kind.value,
            "label": self.label,
            "condition": self.condition,
            "metadata": self.metadata,
            "priority_boost": self.priority_boost,
            "data_key": self.data_key,
        }

    def content_hash(self) -> str:
        return stable_hash(self.definition_payload())

    def __hash__(self) -> int:  # type: ignore[override]
        return int(self.content_hash()[:16], 16)

    def is_blocking(self) -> bool:
        return self.kind in {
            EdgeKind.HARD,
            EdgeKind.DATA,
            EdgeKind.CONTROL,
            EdgeKind.CONDITIONAL,
        }
