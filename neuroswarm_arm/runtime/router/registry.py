"""Versioned tool registry with namespaces and hot updates."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import threading
from typing import Iterable

from .models import ToolRecord
from .router_events import RouterEventBus, RouterEventKind
from .router_exceptions import ToolNotFoundError, ToolValidationError
from .tool_validator import validate_tool_record


def _checksum(tool: ToolRecord) -> str:
    payload = json.dumps(tool.to_dict(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class ToolRegistry:
    def __init__(self, events: RouterEventBus | None = None) -> None:
        self._tools: dict[str, ToolRecord] = {}
        self._versions: dict[str, list[ToolRecord]] = {}
        self._namespaces: dict[str, set[str]] = {}
        self._lock = threading.RLock()
        self.events = events or RouterEventBus()

    def register(self, tool: ToolRecord, *, replace_existing: bool = True) -> ToolRecord:
        validate_tool_record(tool)
        record = replace(tool, checksum=tool.checksum or _checksum(tool))
        with self._lock:
            existing = self._tools.get(record.id)
            if existing and not replace_existing:
                raise ToolValidationError(f"tool already registered: {record.id}")
            if existing:
                self._versions.setdefault(record.id, []).append(existing)
            self._tools[record.id] = record
            self._namespaces.setdefault(record.namespace, set()).add(record.id)
        kind = RouterEventKind.TOOL_UPDATED if existing else RouterEventKind.TOOL_REGISTERED
        self.events.emit(kind, tool_id=record.id, version=record.version)
        return record

    def remove(self, tool_id: str) -> ToolRecord:
        with self._lock:
            if tool_id not in self._tools:
                raise ToolNotFoundError(tool_id)
            tool = self._tools.pop(tool_id)
            ns = self._namespaces.get(tool.namespace)
            if ns is not None:
                ns.discard(tool_id)
        self.events.emit(RouterEventKind.TOOL_REMOVED, tool_id=tool_id)
        return tool

    def update(self, tool_id: str, **fields) -> ToolRecord:
        with self._lock:
            if tool_id not in self._tools:
                raise ToolNotFoundError(tool_id)
            current = self._tools[tool_id]
            data = current.to_dict()
            data.update(fields)
            data["id"] = tool_id
            updated = ToolRecord.from_dict(data)
            return self.register(updated, replace_existing=True)

    def get(self, tool_id: str) -> ToolRecord:
        with self._lock:
            if tool_id not in self._tools:
                raise ToolNotFoundError(tool_id)
            return self._tools[tool_id]

    def get_optional(self, tool_id: str) -> ToolRecord | None:
        with self._lock:
            return self._tools.get(tool_id)

    def as_list(self) -> list[ToolRecord]:
        with self._lock:
            return list(self._tools.values())

    def by_namespace(self, namespace: str) -> list[ToolRecord]:
        with self._lock:
            ids = self._namespaces.get(namespace, set())
            return [self._tools[i] for i in ids if i in self._tools]

    def by_category(self, category: str) -> list[ToolRecord]:
        return [t for t in self.as_list() if t.category == category]

    def by_capability(self, capability: str) -> list[ToolRecord]:
        return [t for t in self.as_list() if capability in t.capabilities]

    def history(self, tool_id: str) -> list[ToolRecord]:
        with self._lock:
            return list(self._versions.get(tool_id, []))

    def bulk_register(self, tools: Iterable[ToolRecord]) -> int:
        count = 0
        for tool in tools:
            self.register(tool)
            count += 1
        return count

    def clear(self) -> None:
        with self._lock:
            self._tools.clear()
            self._namespaces.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._tools)

    def to_dict(self) -> dict[str, dict]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._tools.items()}
