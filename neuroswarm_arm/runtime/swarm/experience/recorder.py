"""Recorder — append completed executions / workflows into the store."""

from __future__ import annotations

from .events import EventBus, ExecutionRecorded, WorkflowRecorded
from .execution_record import ExecutionRecord
from .exceptions import ExperienceStoreError, ValidationError
from .metrics import ExperienceMetrics
from .repository import IExperienceRepository
from .validators import validate_execution_record, validate_workflow_record
from .workflow_record import WorkflowRecord


class ExperienceRecorder:
    """Validate → append → index → emit. Never mutates prior records."""

    def __init__(
        self,
        repository: IExperienceRepository,
        *,
        events: EventBus | None = None,
        metrics: ExperienceMetrics | None = None,
    ) -> None:
        self.repository = repository
        self.events = events or EventBus()
        self.metrics = metrics or ExperienceMetrics()

    def record(self, record: ExecutionRecord) -> ExecutionRecord:
        try:
            validated = validate_execution_record(
                record,
                existing_ids=self.repository.index().all_ids(),
            )
            stored = self.repository.append_execution(validated)
            self.metrics.incr("records_stored")
            self.events.emit(
                ExecutionRecorded(
                    stored.execution_id,
                    stored.workflow_id,
                    success=stored.success,
                    latency=stored.latency,
                    cost=stored.estimated_cost,
                )
            )
            return stored
        except ExperienceStoreError:
            self.metrics.incr("validation_failures")
            raise
        except Exception as exc:
            self.metrics.incr("validation_failures")
            raise ValidationError(str(exc)) from exc

    def record_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        try:
            known = {
                r.execution_id
                for r in self.repository.list_executions(include_archived=True)
            }
            validated = validate_workflow_record(
                record,
                existing_ids={w.workflow_id for w in self.repository.list_workflows()},
                known_execution_ids=known if record.execution_ids else None,
            )
            stored = self.repository.append_workflow(validated)
            self.metrics.incr("workflows_stored")
            self.events.emit(
                WorkflowRecorded(
                    stored.workflow_id,
                    execution_count=len(stored.execution_ids),
                    success=stored.success,
                )
            )
            return stored
        except ExperienceStoreError:
            self.metrics.incr("validation_failures")
            raise

    async def arecord(self, record: ExecutionRecord) -> ExecutionRecord:
        import asyncio

        return await asyncio.to_thread(self.record, record)

    async def arecord_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        import asyncio

        return await asyncio.to_thread(self.record_workflow, record)
