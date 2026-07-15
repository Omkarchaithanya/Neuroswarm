"""Append-only repositories for Experience Store."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from ._utils import new_id, utc_now
from .execution_record import ExecutionRecord
from .exceptions import DuplicateIdError, ImmutabilityError, NotFoundError
from .indexing import ExperienceIndex
from .models import RecordEnvelope, RecordLifecycle
from .workflow_record import WorkflowRecord


@runtime_checkable
class IExperienceRepository(Protocol):
    def append_execution(self, record: ExecutionRecord) -> ExecutionRecord: ...

    def get_execution(self, execution_id: str) -> ExecutionRecord: ...

    def list_executions(self, *, include_archived: bool = False) -> list[ExecutionRecord]: ...

    def append_workflow(self, record: WorkflowRecord) -> WorkflowRecord: ...

    def get_workflow(self, workflow_id: str) -> WorkflowRecord: ...

    def list_workflows(self) -> list[WorkflowRecord]: ...

    def store_snapshot(self, snapshot: Any) -> str: ...

    def load_snapshot(self, handle: str) -> Any: ...

    def archive_execution(self, execution_id: str) -> RecordEnvelope: ...

    def get_envelope(self, execution_id: str) -> RecordEnvelope: ...

    def set_envelope(self, envelope: RecordEnvelope) -> RecordEnvelope: ...

    def index(self) -> ExperienceIndex: ...


class InMemoryRepository:
    """Thread-safe append-only in-memory store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executions: dict[str, ExecutionRecord] = {}
        self._workflows: dict[str, WorkflowRecord] = {}
        self._snapshots: dict[str, Any] = {}
        self._envelopes: dict[str, RecordEnvelope] = {}
        self._archived: dict[str, ExecutionRecord] = {}
        self._index = ExperienceIndex()

    def index(self) -> ExperienceIndex:
        return self._index

    def append_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        with self._lock:
            if record.execution_id in self._executions or record.execution_id in self._archived:
                raise DuplicateIdError(record.execution_id, kind="execution")
            self._executions[record.execution_id] = record
            self._envelopes[record.execution_id] = RecordEnvelope(
                execution_id=record.execution_id,
                lifecycle=RecordLifecycle.RECORDED,
                recorded_at=utc_now(),
            )
            self._index.add(record)
            return record

    def get_execution(self, execution_id: str) -> ExecutionRecord:
        with self._lock:
            if execution_id in self._executions:
                return self._executions[execution_id]
            if execution_id in self._archived:
                return self._archived[execution_id]
            raise NotFoundError(execution_id, kind="execution")

    def list_executions(self, *, include_archived: bool = False) -> list[ExecutionRecord]:
        with self._lock:
            out = list(self._executions.values())
            if include_archived:
                out.extend(self._archived.values())
            return out

    def append_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        with self._lock:
            if record.workflow_id in self._workflows:
                raise DuplicateIdError(record.workflow_id, kind="workflow")
            self._workflows[record.workflow_id] = record
            return record

    def get_workflow(self, workflow_id: str) -> WorkflowRecord:
        with self._lock:
            if workflow_id not in self._workflows:
                raise NotFoundError(workflow_id, kind="workflow")
            return self._workflows[workflow_id]

    def list_workflows(self) -> list[WorkflowRecord]:
        with self._lock:
            return list(self._workflows.values())

    def store_snapshot(self, snapshot: Any) -> str:
        with self._lock:
            sid = new_id("snap_")
            handle = f"exp://snapshot/{sid}"
            if isinstance(snapshot, Mapping):
                payload: Any = dict(snapshot)
            elif hasattr(snapshot, "model_dump"):
                payload = snapshot.model_dump(mode="json")
            else:
                payload = snapshot
            self._snapshots[handle] = payload
            return handle

    def load_snapshot(self, handle: str) -> Any:
        with self._lock:
            if handle not in self._snapshots:
                raise NotFoundError(handle, kind="snapshot")
            return self._snapshots[handle]

    def archive_execution(self, execution_id: str) -> RecordEnvelope:
        with self._lock:
            record = self._executions.pop(execution_id, None)
            if record is None:
                if execution_id in self._archived:
                    return self._envelopes[execution_id]
                raise NotFoundError(execution_id, kind="execution")
            self._archived[execution_id] = record
            self._index.remove_from_active(execution_id)
            env = self._envelopes.get(execution_id)
            if env is None:
                env = RecordEnvelope(execution_id=execution_id)
            updated = RecordEnvelope(
                execution_id=execution_id,
                lifecycle=RecordLifecycle.ARCHIVED,
                recorded_at=env.recorded_at,
                archived_at=utc_now(),
                exported_at=env.exported_at,
                metadata=dict(env.metadata),
            )
            self._envelopes[execution_id] = updated
            return updated

    def get_envelope(self, execution_id: str) -> RecordEnvelope:
        with self._lock:
            if execution_id not in self._envelopes:
                raise NotFoundError(execution_id, kind="envelope")
            return self._envelopes[execution_id]

    def set_envelope(self, envelope: RecordEnvelope) -> RecordEnvelope:
        with self._lock:
            self._envelopes[envelope.execution_id] = envelope
            return envelope

    def update_execution(self, record: ExecutionRecord) -> None:
        raise ImmutabilityError("cannot update execution records")

    def delete_execution(self, execution_id: str) -> None:
        raise ImmutabilityError("cannot delete execution records")


class JsonlRepository(InMemoryRepository):
    """Append-only JSONL persistence with in-memory indexes."""

    def __init__(self, root: str | Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._exec_path = self.root / "executions.jsonl"
        self._workflow_path = self.root / "workflows.jsonl"
        self._snapshot_dir = self.root / "snapshots"
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._archive_path = self.root / "archived_executions.jsonl"
        self._envelope_path = self.root / "envelopes.jsonl"
        self._load()

    def _append_jsonl(self, path: Path, payload: Mapping[str, Any]) -> None:
        line = json.dumps(payload, sort_keys=True, default=str)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def _load(self) -> None:
        self._load_executions(self._exec_path, archived=False)
        self._load_executions(self._archive_path, archived=True)
        if self._workflow_path.exists():
            for line in self._workflow_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                record = WorkflowRecord.model_validate(data)
                self._workflows[record.workflow_id] = record
        if self._envelope_path.exists():
            for line in self._envelope_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                env = RecordEnvelope.model_validate(json.loads(line))
                self._envelopes[env.execution_id] = env
        for snap in self._snapshot_dir.glob("*.json"):
            handle = f"exp://snapshot/{snap.stem}"
            self._snapshots[handle] = json.loads(snap.read_text(encoding="utf-8"))
        self._index.rebuild(self._executions.values())

    def _load_executions(self, path: Path, *, archived: bool) -> None:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = ExecutionRecord.model_validate(json.loads(line))
            if archived:
                self._archived[record.execution_id] = record
            else:
                self._executions[record.execution_id] = record
                if record.execution_id not in self._envelopes:
                    self._envelopes[record.execution_id] = RecordEnvelope(
                        execution_id=record.execution_id,
                        lifecycle=RecordLifecycle.RECORDED,
                    )

    def append_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        with self._lock:
            result = super().append_execution(record)
            self._append_jsonl(
                self._exec_path, result.model_dump(mode="json")
            )
            env = self._envelopes[result.execution_id]
            self._append_jsonl(self._envelope_path, env.model_dump(mode="json"))
            return result

    def append_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        with self._lock:
            result = super().append_workflow(record)
            self._append_jsonl(
                self._workflow_path, result.model_dump(mode="json")
            )
            return result

    def store_snapshot(self, snapshot: Any) -> str:
        with self._lock:
            handle = super().store_snapshot(snapshot)
            sid = handle.rsplit("/", 1)[-1]
            path = self._snapshot_dir / f"{sid}.json"
            payload = self._snapshots[handle]
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            return handle

    def archive_execution(self, execution_id: str) -> RecordEnvelope:
        with self._lock:
            env = super().archive_execution(execution_id)
            record = self._archived[execution_id]
            self._append_jsonl(
                self._archive_path, record.model_dump(mode="json")
            )
            self._append_jsonl(self._envelope_path, env.model_dump(mode="json"))
            return env
