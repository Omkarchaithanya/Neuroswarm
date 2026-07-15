"""Append-only repositories for Checkpoint Manager."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from ._utils import utc_now
from .checkpoint import Checkpoint
from .exceptions import DuplicateCheckpointError, ImmutabilityError, NotFoundError
from .lifecycle import transition
from .models import CheckpointEnvelope, CheckpointStatus


@runtime_checkable
class ICheckpointRepository(Protocol):
    def append(self, checkpoint: Checkpoint) -> Checkpoint: ...

    def get(self, checkpoint_id: str) -> Checkpoint: ...

    def list_by_workflow(
        self, workflow_id: str, *, include_archived: bool = False
    ) -> list[Checkpoint]: ...

    def list_by_execution(
        self, execution_id: str, *, include_archived: bool = False
    ) -> list[Checkpoint]: ...

    def list_all(self, *, include_archived: bool = False) -> list[Checkpoint]: ...

    def latest_for_execution(self, execution_id: str) -> Checkpoint | None: ...

    def latest_for_workflow(self, workflow_id: str) -> Checkpoint | None: ...

    def archive(self, checkpoint_id: str) -> CheckpointEnvelope: ...

    def expire(self, checkpoint_id: str) -> CheckpointEnvelope: ...

    def compact(self, checkpoint_id: str) -> CheckpointEnvelope: ...

    def get_envelope(self, checkpoint_id: str) -> CheckpointEnvelope: ...

    def set_envelope(self, envelope: CheckpointEnvelope) -> CheckpointEnvelope: ...


class InMemoryRepository:
    """Thread-safe append-only in-memory checkpoint store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: dict[str, Checkpoint] = {}
        self._archived: dict[str, Checkpoint] = {}
        self._envelopes: dict[str, CheckpointEnvelope] = {}

    def append(self, checkpoint: Checkpoint) -> Checkpoint:
        with self._lock:
            cid = checkpoint.checkpoint_id
            if cid in self._active or cid in self._archived:
                raise DuplicateCheckpointError(cid)
            self._active[cid] = checkpoint
            self._envelopes[cid] = CheckpointEnvelope(
                checkpoint_id=cid,
                status=CheckpointStatus.ACTIVE,
                recorded_at=utc_now(),
            )
            return checkpoint

    def get(self, checkpoint_id: str) -> Checkpoint:
        with self._lock:
            if checkpoint_id in self._active:
                return self._active[checkpoint_id]
            if checkpoint_id in self._archived:
                return self._archived[checkpoint_id]
            raise NotFoundError(checkpoint_id, kind="checkpoint")

    def list_by_workflow(
        self, workflow_id: str, *, include_archived: bool = False
    ) -> list[Checkpoint]:
        return [
            c
            for c in self.list_all(include_archived=include_archived)
            if c.workflow_id == workflow_id
        ]

    def list_by_execution(
        self, execution_id: str, *, include_archived: bool = False
    ) -> list[Checkpoint]:
        return [
            c
            for c in self.list_all(include_archived=include_archived)
            if c.execution_id == execution_id
        ]

    def list_all(self, *, include_archived: bool = False) -> list[Checkpoint]:
        with self._lock:
            out = list(self._active.values())
            if include_archived:
                out.extend(self._archived.values())
            return out

    def latest_for_execution(self, execution_id: str) -> Checkpoint | None:
        items = self.list_by_execution(execution_id)
        if not items:
            return None
        return max(items, key=lambda c: c.timestamp)

    def latest_for_workflow(self, workflow_id: str) -> Checkpoint | None:
        items = self.list_by_workflow(workflow_id)
        if not items:
            return None
        return max(items, key=lambda c: c.timestamp)

    def archive(self, checkpoint_id: str) -> CheckpointEnvelope:
        return self._transition(checkpoint_id, CheckpointStatus.ARCHIVED)

    def expire(self, checkpoint_id: str) -> CheckpointEnvelope:
        return self._transition(checkpoint_id, CheckpointStatus.EXPIRED)

    def compact(self, checkpoint_id: str) -> CheckpointEnvelope:
        return self._transition(checkpoint_id, CheckpointStatus.COMPACTED)

    def get_envelope(self, checkpoint_id: str) -> CheckpointEnvelope:
        with self._lock:
            if checkpoint_id not in self._envelopes:
                raise NotFoundError(checkpoint_id, kind="envelope")
            return self._envelopes[checkpoint_id]

    def set_envelope(self, envelope: CheckpointEnvelope) -> CheckpointEnvelope:
        with self._lock:
            if envelope.checkpoint_id not in self._envelopes:
                raise NotFoundError(envelope.checkpoint_id, kind="envelope")
            self._envelopes[envelope.checkpoint_id] = envelope
            return envelope

    def _transition(
        self, checkpoint_id: str, target: CheckpointStatus
    ) -> CheckpointEnvelope:
        with self._lock:
            ckpt = self._active.get(checkpoint_id) or self._archived.get(checkpoint_id)
            if ckpt is None:
                raise NotFoundError(checkpoint_id, kind="checkpoint")
            env = self._envelopes.get(checkpoint_id)
            if env is None:
                env = CheckpointEnvelope(checkpoint_id=checkpoint_id)
            new_status = transition(checkpoint_id, env.status, target)
            if checkpoint_id in self._active and target in {
                CheckpointStatus.ARCHIVED,
                CheckpointStatus.EXPIRED,
                CheckpointStatus.COMPACTED,
            }:
                self._archived[checkpoint_id] = self._active.pop(checkpoint_id)
            updated = CheckpointEnvelope(
                checkpoint_id=checkpoint_id,
                status=new_status,
                recorded_at=env.recorded_at,
                archived_at=utc_now()
                if new_status == CheckpointStatus.ARCHIVED
                else env.archived_at,
                expired_at=utc_now()
                if new_status == CheckpointStatus.EXPIRED
                else env.expired_at,
                compacted_at=utc_now()
                if new_status == CheckpointStatus.COMPACTED
                else env.compacted_at,
                metadata=dict(env.metadata),
            )
            self._envelopes[checkpoint_id] = updated
            return updated


class JsonlRepository(InMemoryRepository):
    """Append-only JSONL-backed repository (loads into memory on init)."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load()

    def append(self, checkpoint: Checkpoint) -> Checkpoint:
        result = super().append(checkpoint)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(checkpoint.model_dump(mode="json"), default=str) + "\n"
                )
        return result

    def set_envelope(self, envelope: CheckpointEnvelope) -> CheckpointEnvelope:
        # Envelope mutations are in-memory; physical rewrite deferred (no hard delete).
        return super().set_envelope(envelope)

    def _load(self) -> None:
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                ckpt = Checkpoint.model_validate(data)
                try:
                    super().append(ckpt)
                except DuplicateCheckpointError as exc:
                    raise ImmutabilityError(str(exc)) from exc
