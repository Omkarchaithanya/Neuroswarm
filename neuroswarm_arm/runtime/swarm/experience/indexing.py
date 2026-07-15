"""Secondary indexes over immutable execution records."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from threading import RLock
from typing import Iterable

from .execution_record import ExecutionRecord


class ExperienceIndex:
    """In-memory secondary indexes for query acceleration."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.by_execution: dict[str, ExecutionRecord] = {}
        self.by_workflow: dict[str, set[str]] = defaultdict(set)
        self.by_request: dict[str, set[str]] = defaultdict(set)
        self.by_agent: dict[str, set[str]] = defaultdict(set)
        self.by_model: dict[str, set[str]] = defaultdict(set)
        self.by_backend: dict[str, set[str]] = defaultdict(set)
        self.by_success: dict[bool, set[str]] = defaultdict(set)
        self.by_tag: dict[str, set[str]] = defaultdict(set)
        # sorted lists of (value, execution_id) for range filters
        self.latency_entries: list[tuple[float, str]] = []
        self.cost_entries: list[tuple[float, str]] = []
        self.quality_entries: list[tuple[float, str]] = []
        self.timestamp_entries: list[tuple[datetime, str]] = []

    def clear(self) -> None:
        with self._lock:
            self.by_execution.clear()
            self.by_workflow.clear()
            self.by_request.clear()
            self.by_agent.clear()
            self.by_model.clear()
            self.by_backend.clear()
            self.by_success.clear()
            self.by_tag.clear()
            self.latency_entries.clear()
            self.cost_entries.clear()
            self.quality_entries.clear()
            self.timestamp_entries.clear()

    def add(self, record: ExecutionRecord) -> None:
        with self._lock:
            eid = record.execution_id
            if eid in self.by_execution:
                return
            self.by_execution[eid] = record
            self.by_workflow[record.workflow_id].add(eid)
            if record.request_id:
                self.by_request[record.request_id].add(eid)
            for assignment in record.agent_assignments:
                self.by_agent[assignment.agent_id].add(eid)
            for model in record.models_used:
                self.by_model[model].add(eid)
            for backend in record.backends_used:
                self.by_backend[backend].add(eid)
            self.by_success[record.success].add(eid)
            for tag in record.tags:
                self.by_tag[tag].add(eid)
            self.latency_entries.append((record.latency, eid))
            self.cost_entries.append((record.estimated_cost, eid))
            self.quality_entries.append((record.quality_score.score, eid))
            self.timestamp_entries.append((record.timestamp, eid))

    def remove_from_active(self, execution_id: str) -> ExecutionRecord | None:
        """Drop from active indexes (archive path). Record body remains immutable."""
        with self._lock:
            record = self.by_execution.pop(execution_id, None)
            if record is None:
                return None
            self.by_workflow[record.workflow_id].discard(execution_id)
            if record.request_id:
                self.by_request[record.request_id].discard(execution_id)
            for assignment in record.agent_assignments:
                self.by_agent[assignment.agent_id].discard(execution_id)
            for model in record.models_used:
                self.by_model[model].discard(execution_id)
            for backend in record.backends_used:
                self.by_backend[backend].discard(execution_id)
            self.by_success[record.success].discard(execution_id)
            for tag in record.tags:
                self.by_tag[tag].discard(execution_id)
            self.latency_entries = [
                e for e in self.latency_entries if e[1] != execution_id
            ]
            self.cost_entries = [e for e in self.cost_entries if e[1] != execution_id]
            self.quality_entries = [
                e for e in self.quality_entries if e[1] != execution_id
            ]
            self.timestamp_entries = [
                e for e in self.timestamp_entries if e[1] != execution_id
            ]
            return record

    def compact(self) -> None:
        """Drop empty secondary sets and re-sort range entries."""
        with self._lock:
            for mapping in (
                self.by_workflow,
                self.by_request,
                self.by_agent,
                self.by_model,
                self.by_backend,
                self.by_tag,
            ):
                empty = [k for k, v in mapping.items() if not v]
                for k in empty:
                    del mapping[k]
            self.latency_entries.sort(key=lambda t: t[0])
            self.cost_entries.sort(key=lambda t: t[0])
            self.quality_entries.sort(key=lambda t: t[0])
            self.timestamp_entries.sort(key=lambda t: t[0])

    def rebuild(self, records: Iterable[ExecutionRecord]) -> None:
        self.clear()
        for record in records:
            self.add(record)
        self.compact()

    def get(self, execution_id: str) -> ExecutionRecord | None:
        return self.by_execution.get(execution_id)

    def all_ids(self) -> set[str]:
        return set(self.by_execution.keys())
