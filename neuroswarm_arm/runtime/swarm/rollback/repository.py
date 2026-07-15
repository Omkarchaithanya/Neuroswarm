"""Append-only repositories for Rollback Manager."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from .exceptions import DuplicateRollbackError, ImmutabilityError, NotFoundError
from .metadata import RollbackExecutionMetadata
from .models import RollbackStatus
from .rollback import RollbackOperation


@runtime_checkable
class IRollbackRepository(Protocol):
    def append(self, operation: RollbackOperation) -> RollbackOperation: ...

    def get(self, rollback_id: str) -> RollbackOperation: ...

    def list_by_workflow(self, workflow_id: str) -> list[RollbackOperation]: ...

    def list_by_execution(self, execution_id: str) -> list[RollbackOperation]: ...

    def list_all(self) -> list[RollbackOperation]: ...

    def get_metadata(self, rollback_id: str) -> RollbackExecutionMetadata: ...

    def set_metadata(
        self, metadata: RollbackExecutionMetadata
    ) -> RollbackExecutionMetadata: ...


class InMemoryRepository:
    """Thread-safe append-only in-memory rollback store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ops: dict[str, RollbackOperation] = {}
        self._meta: dict[str, RollbackExecutionMetadata] = {}

    def append(self, operation: RollbackOperation) -> RollbackOperation:
        with self._lock:
            rid = operation.rollback_id
            if rid in self._ops:
                raise DuplicateRollbackError(rid)
            self._ops[rid] = operation
            self._meta[rid] = RollbackExecutionMetadata(
                rollback_id=rid,
                status=operation.status,
            )
            return operation

    def get(self, rollback_id: str) -> RollbackOperation:
        with self._lock:
            if rollback_id not in self._ops:
                raise NotFoundError(rollback_id, kind="rollback")
            return self._ops[rollback_id]

    def list_by_workflow(self, workflow_id: str) -> list[RollbackOperation]:
        return [o for o in self.list_all() if o.workflow_id == workflow_id]

    def list_by_execution(self, execution_id: str) -> list[RollbackOperation]:
        return [o for o in self.list_all() if o.execution_id == execution_id]

    def list_all(self) -> list[RollbackOperation]:
        with self._lock:
            return list(self._ops.values())

    def get_metadata(self, rollback_id: str) -> RollbackExecutionMetadata:
        with self._lock:
            if rollback_id not in self._meta:
                raise NotFoundError(rollback_id, kind="metadata")
            return self._meta[rollback_id]

    def set_metadata(
        self, metadata: RollbackExecutionMetadata
    ) -> RollbackExecutionMetadata:
        with self._lock:
            if metadata.rollback_id not in self._ops:
                raise NotFoundError(metadata.rollback_id, kind="rollback")
            self._meta[metadata.rollback_id] = metadata
            # Store updated status on a new operation envelope via replace
            op = self._ops[metadata.rollback_id]
            if op.status != metadata.status:
                self._ops[metadata.rollback_id] = op.with_status(metadata.status)
            return metadata

    def update_status(
        self, rollback_id: str, status: RollbackStatus
    ) -> RollbackOperation:
        with self._lock:
            op = self.get(rollback_id)
            updated = op.with_status(status)
            self._ops[rollback_id] = updated
            meta = self._meta.get(rollback_id)
            if meta is not None:
                data = meta.model_dump(mode="python")
                data["status"] = status
                self._meta[rollback_id] = RollbackExecutionMetadata.model_validate(data)
            return updated


class JsonlRepository(InMemoryRepository):
    """Append-only JSONL-backed repository (loads into memory on init)."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load()

    def append(self, operation: RollbackOperation) -> RollbackOperation:
        result = super().append(operation)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(operation.model_dump(mode="json"), default=str) + "\n"
                )
        return result

    def _load(self) -> None:
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                op = RollbackOperation.model_validate(data)
                try:
                    super().append(op)
                except DuplicateRollbackError as exc:
                    raise ImmutabilityError(str(exc)) from exc
