"""SubSwarmRegistry — in-memory catalog of swarm templates."""

from __future__ import annotations

import threading
from typing import Any, Callable

from ._utils import utc_now
from .events import EventBus, SwarmArchived, SwarmDeprecated, SwarmDisabled, SwarmRegistered, SwarmUpdated
from .exceptions import DuplicateTemplateError, LifecycleError, TemplateNotFoundError
from .lifecycle import LifecycleState, can_transition, is_selectable, transition
from .metrics import SwarmMetrics
from .template import SwarmTemplate
from .validator import SwarmValidator


def _promotion_path(
    current: LifecycleState, target: LifecycleState
) -> list[LifecycleState]:
    """Return intermediate+target states for a legal promotion, or raise."""
    if current is target:
        return []
    if can_transition(current, target):
        return [target]
    # Common template bootstrap: CREATED → REGISTERED → READY
    bootstrap = [
        LifecycleState.CREATED,
        LifecycleState.REGISTERED,
        LifecycleState.READY,
    ]
    if current in bootstrap and target in bootstrap:
        ci = bootstrap.index(current)
        ti = bootstrap.index(target)
        if ti > ci:
            return bootstrap[ci + 1 : ti + 1]
    raise LifecycleError("bootstrap", current, target)


class SubSwarmRegistry:
    """CRUD + indexed lookup for SwarmTemplate records."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: SwarmMetrics | None = None,
        validator: SwarmValidator | None = None,
        on_change: Callable[[], None] | None = None,
        validate_on_register: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, SwarmTemplate] = {}
        self._by_name: dict[str, str] = {}
        self._by_category: dict[str, set[str]] = {}
        self._by_workflow: dict[str, set[str]] = {}
        self._by_tag: dict[str, set[str]] = {}
        self.events = events
        self.metrics = metrics
        self.validator = validator or SwarmValidator()
        self._on_change = on_change
        self.validate_on_register = validate_on_register

    def register(
        self,
        template: SwarmTemplate,
        *,
        promote_to: LifecycleState | None = LifecycleState.REGISTERED,
        strict: bool = False,
    ) -> SwarmTemplate:
        with self._lock:
            if template.id in self._by_id:
                raise DuplicateTemplateError(
                    f"template id already registered: {template.id}",
                    field="id",
                )
            if template.name in self._by_name:
                raise DuplicateTemplateError(
                    f"template name already registered: {template.name}",
                    field="name",
                )
            if self.validate_on_register:
                self.validator.validate(template, registry=self, strict=strict)

            record = template
            if promote_to is not None and record.status is not promote_to:
                # Walk allowed path when possible (e.g. CREATED → REGISTERED → READY).
                path = _promotion_path(record.status, promote_to)
                for step in path:
                    record = record.evolve(status=step)

            self._by_id[record.id] = record
            self._by_name[record.name] = record.id
            self._index_add(record)

        if self.metrics is not None:
            self.metrics.record_registration(category=record.category)
        if self.events is not None:
            self.events.emit(
                SwarmRegistered(
                    record.id,
                    name=record.name,
                    category=record.category,
                    version=record.version,
                )
            )
        self._notify()
        return record

    def unregister(self, template_id: str) -> SwarmTemplate:
        with self._lock:
            record = self._require(template_id)
            self._index_remove(record)
            del self._by_id[template_id]
            self._by_name.pop(record.name, None)
        self._notify()
        return record

    def replace(self, template_id: str, template: SwarmTemplate) -> SwarmTemplate:
        with self._lock:
            old = self._require(template_id)
            if template.id != template_id:
                raise DuplicateTemplateError(
                    "replacement id must match existing id",
                    field="id",
                )
            if template.name != old.name and template.name in self._by_name:
                raise DuplicateTemplateError(
                    f"template name already registered: {template.name}",
                    field="name",
                )
            self._index_remove(old)
            self._by_name.pop(old.name, None)
            record = template.touch()
            self._by_id[template_id] = record
            self._by_name[record.name] = template_id
            self._index_add(record)
        if self.events is not None:
            self.events.emit(SwarmUpdated(template_id, name=record.name))
        self._notify()
        return record

    def update(self, template_id: str, **fields: Any) -> SwarmTemplate:
        with self._lock:
            current = self._require(template_id)
            if "name" in fields and fields["name"] != current.name:
                if fields["name"] in self._by_name:
                    raise DuplicateTemplateError(
                        f"template name already registered: {fields['name']}",
                        field="name",
                    )
            self._index_remove(current)
            self._by_name.pop(current.name, None)
            record = current.evolve(**fields)
            self._by_id[template_id] = record
            self._by_name[record.name] = template_id
            self._index_add(record)
        if self.events is not None:
            self.events.emit(SwarmUpdated(template_id, fields=list(fields.keys())))
        self._notify()
        return record

    def set_status(self, template_id: str, target: LifecycleState) -> SwarmTemplate:
        with self._lock:
            current = self._require(template_id)
            new_status = transition(template_id, current.status, target)
            record = current.evolve(status=new_status)
            self._index_remove(current)
            self._by_id[template_id] = record
            self._index_add(record)
        if self.events is not None:
            if target is LifecycleState.DEPRECATED:
                self.events.emit(SwarmDeprecated(template_id))
            elif target is LifecycleState.ARCHIVED:
                self.events.emit(SwarmArchived(template_id))
            elif target is LifecycleState.DISABLED:
                self.events.emit(SwarmDisabled(template_id))
            else:
                self.events.emit(SwarmUpdated(template_id, status=target.value))
        self._notify()
        return record

    def get(self, template_id: str) -> SwarmTemplate:
        with self._lock:
            return self._require(template_id)

    def get_optional(self, template_id: str) -> SwarmTemplate | None:
        with self._lock:
            return self._by_id.get(template_id)

    def get_by_name(self, name: str) -> SwarmTemplate:
        with self._lock:
            tid = self._by_name.get(name)
            if tid is None:
                raise TemplateNotFoundError(name)
            return self._by_id[tid]

    def as_list(self) -> list[SwarmTemplate]:
        with self._lock:
            return list(self._by_id.values())

    def list_ready(self) -> list[SwarmTemplate]:
        return [t for t in self.as_list() if is_selectable(t.status)]

    def lookup_by_category(self, category: str) -> list[SwarmTemplate]:
        with self._lock:
            ids = self._by_category.get(category, set())
            return [self._by_id[i] for i in ids if i in self._by_id]

    def lookup_by_workflow(self, workflow_type: str) -> list[SwarmTemplate]:
        with self._lock:
            ids = self._by_workflow.get(workflow_type, set())
            return [self._by_id[i] for i in ids if i in self._by_id]

    def lookup_by_tag(self, tag: str) -> list[SwarmTemplate]:
        with self._lock:
            ids = self._by_tag.get(tag.lower(), set())
            return [self._by_id[i] for i in ids if i in self._by_id]

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_id)

    def __contains__(self, template_id: str) -> bool:
        with self._lock:
            return template_id in self._by_id

    def _require(self, template_id: str) -> SwarmTemplate:
        record = self._by_id.get(template_id)
        if record is None:
            raise TemplateNotFoundError(template_id)
        return record

    def _index_add(self, record: SwarmTemplate) -> None:
        self._by_category.setdefault(record.category, set()).add(record.id)
        if record.workflow_type:
            self._by_workflow.setdefault(record.workflow_type, set()).add(record.id)
        for tag in record.tags:
            self._by_tag.setdefault(tag, set()).add(record.id)

    def _index_remove(self, record: SwarmTemplate) -> None:
        if record.category in self._by_category:
            self._by_category[record.category].discard(record.id)
        if record.workflow_type in self._by_workflow:
            self._by_workflow[record.workflow_type].discard(record.id)
        for tag in record.tags:
            if tag in self._by_tag:
                self._by_tag[tag].discard(record.id)

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
