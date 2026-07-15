"""Tags, labels, and ownership helpers for swarm templates."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SwarmMetadata(_Base):
    """Extensible metadata bag with normalized tags/labels."""

    owner: str = ""
    team: str = ""
    source: str = "platform"
    provenance: list[str] = Field(default_factory=list)
    composition_of: list[str] = Field(default_factory=list)
    notes: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provenance", "composition_of", mode="before")
    @classmethod
    def _listify(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)  # type: ignore[arg-type]


def normalize_tags(tags: Sequence[str] | None) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        key = str(t).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def normalize_labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    if not labels:
        return {}
    return {str(k).strip(): str(v).strip() for k, v in labels.items() if str(k).strip()}


def merge_tags(*groups: Sequence[str] | None) -> list[str]:
    merged: list[str] = []
    for g in groups:
        merged.extend(normalize_tags(g))
    return normalize_tags(merged)


def merge_labels(*groups: Mapping[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for g in groups:
        out.update(normalize_labels(g))
    return out
