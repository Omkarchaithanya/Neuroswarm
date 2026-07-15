"""Runtime event envelopes published on the HAOE EventBus."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Mapping
from uuid import uuid4

from ..interfaces.types import CorrelationIds, TaskState


@dataclass(slots=True)
class RuntimeEvent:
    topic: str
    name: str
    ids: CorrelationIds = field(default_factory=CorrelationIds)
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time)
    event_id: str = field(default_factory=lambda: uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "name": self.name,
            "ids": self.ids.to_dict(),
            "payload": self.payload,
            "ts": self.ts,
            "event_id": self.event_id,
        }


def task_event(
    event_name: str,
    *,
    task_id: str,
    state: TaskState,
    ids: CorrelationIds | None = None,
    **payload: Any,
) -> RuntimeEvent:
    body = {"task_id": task_id, "state": state.value, **payload}
    return RuntimeEvent(
        topic="haoe.task",
        name=event_name,
        ids=ids or CorrelationIds(),
        payload=body,
    )


def workflow_event(
    event_name: str,
    *,
    workflow_id: str,
    ids: CorrelationIds | None = None,
    **payload: Any,
) -> RuntimeEvent:
    body = {"workflow_id": workflow_id, **payload}
    return RuntimeEvent(
        topic="haoe.workflow",
        name=event_name,
        ids=ids or CorrelationIds(workflow_id=workflow_id),
        payload=body,
    )


def lifecycle_event(name: str, **payload: Any) -> RuntimeEvent:
    return RuntimeEvent(topic="haoe.lifecycle", name=name, payload=dict(payload))


def as_mapping(event: RuntimeEvent) -> Mapping[str, Any]:
    return event.to_dict()
