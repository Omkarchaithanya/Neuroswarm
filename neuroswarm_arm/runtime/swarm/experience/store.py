"""ExperienceStore facade + build_experience_store() DI factory."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Mapping

from .analytics import AnalyticsReport, ExperienceAnalytics
from .dataset import DatasetGenerator, ExperienceDataset
from .events import EventBus
from .execution_record import ExecutionRecord
from .exporter import ExperienceExporter
from .filters import ExperienceFilter
from .importer import ExperienceImporter
from .metrics import ExperienceMetrics
from .models import DatasetKind, ExportFormat, RecordEnvelope
from .query import QueryEngine
from .recorder import ExperienceRecorder
from .repository import InMemoryRepository, IExperienceRepository, JsonlRepository
from .retention import RetentionManager, RetentionPolicy
from .serializer import ExperienceSerializer
from .validators import validate_snapshot_payload
from .workflow_record import WorkflowRecord


class ExperienceStore:
    """Immutable historical execution database for NEXUS-ARM swarm plane.

    Distinct from ``neuroswarm_arm.evolution.rl.experience_store.ExperienceStore``
    (AROP offline RL tuples). This store records completed workflow executions.
    """

    def __init__(
        self,
        repository: IExperienceRepository | None = None,
        *,
        events: EventBus | None = None,
        metrics: ExperienceMetrics | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or ExperienceMetrics()
        self.repository = repository or InMemoryRepository()
        self.recorder = ExperienceRecorder(
            self.repository, events=self.events, metrics=self.metrics
        )
        self.query = QueryEngine(self.repository, metrics=self.metrics)
        self.analytics = ExperienceAnalytics(
            self.query, events=self.events, metrics=self.metrics
        )
        self.retention = RetentionManager(
            self.repository, events=self.events, metrics=self.metrics
        )
        self.exporter = ExperienceExporter(events=self.events, metrics=self.metrics)
        self.importer = ExperienceImporter(
            self.recorder, events=self.events, metrics=self.metrics
        )
        self.datasets = DatasetGenerator()
        self.serializer = ExperienceSerializer()

    # ---- recording ----
    def record(self, record: ExecutionRecord) -> ExecutionRecord:
        return self.recorder.record(record)

    def record_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        return self.recorder.record_workflow(record)

    async def arecord(self, record: ExecutionRecord) -> ExecutionRecord:
        return await self.recorder.arecord(record)

    # ---- IExperienceStorePort / ISwarmContextExperiencePort ----
    def store_snapshot(self, snapshot: Any) -> str:
        validate_snapshot_payload(snapshot)
        handle = self.repository.store_snapshot(snapshot)
        self.metrics.incr("snapshots_stored")
        return handle

    def load_snapshot(self, handle: str) -> Any:
        return self.repository.load_snapshot(handle)

    # ---- IHaoeExperiencePort ----
    def record_workflow_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        return self.record(record)

    # ---- ITaskGraphExperiencePort ----
    def record_graph_execution(
        self,
        *,
        task_graph_reference: str,
        execution: ExecutionRecord,
    ) -> ExecutionRecord:
        data = execution.model_dump(mode="json")
        data["task_graph_reference"] = task_graph_reference
        data["content_hash"] = None
        return self.record(ExecutionRecord.model_validate(data))

    # ---- IWorkflowCoordinationPort ----
    # record_workflow already defined

    # ---- IDashboardExperiencePort ----
    def export_metrics(self) -> Mapping[str, float]:
        return {k: float(v) for k, v in self.metrics.snapshot().items()}

    # ---- IBenchmarkRuntimePort / IPolicyEnginePort ----
    def generate_benchmark_dataset(
        self, filt: ExperienceFilter | None = None
    ) -> ExperienceDataset:
        return self.datasets.benchmark(self.query.filter(filt))

    def generate_policy_dataset(
        self, filt: ExperienceFilter | None = None
    ) -> ExperienceDataset:
        return self.datasets.policy(self.query.filter(filt))

    def generate_offline_rl_dataset(
        self, filt: ExperienceFilter | None = None
    ) -> ExperienceDataset:
        return self.datasets.offline_rl(self.query.filter(filt))

    def generate_analytics_dataset(
        self, filt: ExperienceFilter | None = None
    ) -> ExperienceDataset:
        return self.datasets.analytics(self.query.filter(filt))

    def generate_dataset(
        self,
        kind: DatasetKind | str,
        filt: ExperienceFilter | None = None,
    ) -> ExperienceDataset:
        return self.datasets.generate(kind, self.query.filter(filt))

    # ---- analytics / retention / export ----
    def compute_analytics(
        self, filt: ExperienceFilter | None = None
    ) -> AnalyticsReport:
        return self.analytics.compute(filt)

    def apply_retention(self, policy: RetentionPolicy) -> dict[str, Any]:
        return self.retention.apply(policy)

    def archive(self, execution_id: str) -> RecordEnvelope:
        return self.retention.archive(execution_id)

    def export(
        self,
        filt: ExperienceFilter | None = None,
        *,
        fmt: ExportFormat | str = ExportFormat.JSON,
        path: str | Path | None = None,
    ) -> str | Path:
        return self.exporter.export_records(
            self.query.filter(filt), fmt=fmt, path=path
        )

    def export_dataset(
        self,
        kind: DatasetKind | str,
        *,
        filt: ExperienceFilter | None = None,
        fmt: ExportFormat | str = ExportFormat.JSON,
        path: str | Path | None = None,
    ) -> str | Path:
        ds = self.generate_dataset(kind, filt)
        return self.exporter.export_dataset(ds, fmt=fmt, path=path)

    def get(self, execution_id: str) -> ExecutionRecord:
        return self.query.get(execution_id)

    def filter(self, filt: ExperienceFilter | None = None) -> list[ExecutionRecord]:
        return self.query.filter(filt)

    async def afilter(
        self, filt: ExperienceFilter | None = None
    ) -> list[ExecutionRecord]:
        return await self.query.afilter(filt)

    async def acompute_analytics(
        self, filt: ExperienceFilter | None = None
    ) -> AnalyticsReport:
        return await asyncio.to_thread(self.compute_analytics, filt)


def build_experience_store(
    *,
    root: str | Path | None = None,
    events: EventBus | None = None,
    metrics: ExperienceMetrics | None = None,
) -> ExperienceStore:
    """DI factory — in-memory by default, JSONL when ``root`` is set."""
    repo: IExperienceRepository
    if root is not None:
        repo = JsonlRepository(root)
    else:
        repo = InMemoryRepository()
    return ExperienceStore(repo, events=events, metrics=metrics)
