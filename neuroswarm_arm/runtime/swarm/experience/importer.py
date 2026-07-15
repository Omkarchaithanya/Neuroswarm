"""Importer — validated append-only ingest of external experience payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .events import EventBus, ExecutionRecorded
from .exceptions import ImportError as ExperienceImportError
from .exceptions import ImmutabilityError
from .execution_record import ExecutionRecord
from .metrics import ExperienceMetrics
from .recorder import ExperienceRecorder
from .serializer import ExperienceSerializer, migrate
from .workflow_record import WorkflowRecord


class ExperienceImporter:
    """Import records into the store (append only — never overwrite)."""

    def __init__(
        self,
        recorder: ExperienceRecorder,
        *,
        events: EventBus | None = None,
        metrics: ExperienceMetrics | None = None,
        serializer: ExperienceSerializer | None = None,
    ) -> None:
        self.recorder = recorder
        self.events = events or recorder.events
        self.metrics = metrics or recorder.metrics
        self.serializer = serializer or ExperienceSerializer()

    def import_record(self, payload: ExecutionRecord | dict[str, Any]) -> ExecutionRecord:
        record = (
            payload
            if isinstance(payload, ExecutionRecord)
            else ExecutionRecord.model_validate(migrate(payload).get("data", payload))
        )
        stored = self.recorder.record(record)
        self.metrics.incr("import_operations")
        return stored

    def import_records(
        self, payloads: Sequence[ExecutionRecord | dict[str, Any]]
    ) -> list[ExecutionRecord]:
        return [self.import_record(p) for p in payloads]

    def import_json(self, raw: str) -> list[ExecutionRecord]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExperienceImportError(str(exc)) from exc
        if isinstance(data, dict) and "data" in data and "kind" in data:
            obj = self.serializer.loads(raw, fmt="json")
            if isinstance(obj, ExecutionRecord):
                return [self.import_record(obj)]
            if isinstance(obj, WorkflowRecord):
                self.recorder.record_workflow(obj)
                return []
            raise ExperienceImportError(f"unsupported kind in payload")
        if isinstance(data, list):
            return self.import_records(data)
        if isinstance(data, dict):
            return [self.import_record(data)]
        raise ExperienceImportError("JSON payload must be object or array")

    def import_file(self, path: str | Path) -> list[ExecutionRecord]:
        p = Path(path)
        if not p.exists():
            raise ExperienceImportError(f"file not found: {p}")
        if p.suffix.lower() == ".jsonl":
            records: list[ExecutionRecord] = []
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                records.extend(self.import_json(line))
            return records
        return self.import_json(p.read_text(encoding="utf-8"))

    def replace_record(self, record: ExecutionRecord) -> None:
        raise ImmutabilityError("import cannot replace existing records")
