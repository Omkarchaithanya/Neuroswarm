"""Input validators for Cognitive Memory Runtime."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.exceptions import MemoryValidationError
from neuroswarm_arm.runtime.memory.namespace import normalize_namespace
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, MemoryType, SearchQuery


def validate_owner(owner: str) -> str:
    value = (owner or "").strip()
    if not value or value.isspace():
        raise MemoryValidationError("owner must be non-empty")
    if " " in value:
        raise MemoryValidationError("owner must not contain spaces")
    return value


def validate_content(content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise MemoryValidationError("content must be non-empty")
    return text


def validate_score(name: str, value: float, *, lo: float = 0.0, hi: float = 1.0) -> float:
    if value < lo or value > hi:
        raise MemoryValidationError(f"{name} must be in [{lo}, {hi}], got {value}")
    return value


def validate_record(record: MemoryRecord) -> MemoryRecord:
    record.owner = validate_owner(record.owner)
    record.content = validate_content(record.content)
    record.namespace = normalize_namespace(record.namespace)
    if not isinstance(record.type, MemoryType):
        record.type = MemoryType(str(record.type))
    record.importance = validate_score("importance", float(record.importance))
    record.confidence = validate_score("confidence", float(record.confidence))
    return record


def validate_query(query: SearchQuery) -> SearchQuery:
    query.owner = validate_owner(query.owner) if query.owner else "default"
    query.text = validate_content(query.text) if query.text.strip() else "context"
    if query.namespace:
        query.namespace = normalize_namespace(query.namespace)
    if query.limit < 1:
        raise MemoryValidationError("limit must be >= 1")
    return query
