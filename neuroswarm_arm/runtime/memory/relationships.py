"""Relationship linking between memories."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord


class RelationshipManager:
    def link(self, a: MemoryRecord, b: MemoryRecord, *, rel: str = "related") -> None:
        if b.uuid not in a.relationships:
            a.relationships.append(b.uuid)
        if a.uuid not in b.relationships:
            b.relationships.append(a.uuid)
        a.metadata.setdefault("links", {})
        b.metadata.setdefault("links", {})
        if isinstance(a.metadata["links"], dict):
            a.metadata["links"][b.uuid] = rel
        if isinstance(b.metadata["links"], dict):
            b.metadata["links"][a.uuid] = rel

    def neighbors(self, record: MemoryRecord, catalog: dict[str, MemoryRecord]) -> list[MemoryRecord]:
        return [catalog[i] for i in record.relationships if i in catalog]
