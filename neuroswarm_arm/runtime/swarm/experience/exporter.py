"""Exporters — CSV / JSON / Parquet / OpenTelemetry-compatible shapes."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Sequence

from .dataset import ExperienceDataset
from .events import DatasetGenerated, EventBus, ExecutionExported
from .exceptions import ExportError
from .execution_record import ExecutionRecord
from .metrics import ExperienceMetrics
from .models import ExportFormat


class ExperienceExporter:
    """Export records and datasets to portable formats."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: ExperienceMetrics | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or ExperienceMetrics()

    def export_records(
        self,
        records: Sequence[ExecutionRecord],
        *,
        fmt: ExportFormat | str = ExportFormat.JSON,
        path: str | Path | None = None,
    ) -> str | Path:
        fmt = ExportFormat(fmt) if isinstance(fmt, str) else fmt
        if fmt is ExportFormat.JSON:
            payload = [r.model_dump(mode="json") for r in records]
            text = json.dumps(payload, indent=2, sort_keys=True, default=str)
            return self._write_or_return(text, path, suffix=".json")
        if fmt is ExportFormat.CSV:
            rows = [self._flat_record(r) for r in records]
            text = self._to_csv(rows)
            return self._write_or_return(text, path, suffix=".csv")
        if fmt is ExportFormat.YAML:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise ExportError("PyYAML required for yaml export") from exc
            payload = [r.model_dump(mode="json") for r in records]
            text = yaml.safe_dump(payload, sort_keys=True, default_flow_style=False)
            return self._write_or_return(text, path, suffix=".yaml")
        if fmt is ExportFormat.OTEL:
            payload = [self._otel_span_like(r) for r in records]
            text = json.dumps(payload, indent=2, sort_keys=True, default=str)
            return self._write_or_return(text, path, suffix=".otel.json")
        if fmt is ExportFormat.PARQUET:
            return self._export_parquet(
                [self._flat_record(r) for r in records], path
            )
        raise ExportError(f"unsupported format: {fmt}")

    def export_dataset(
        self,
        dataset: ExperienceDataset,
        *,
        fmt: ExportFormat | str = ExportFormat.JSON,
        path: str | Path | None = None,
    ) -> str | Path:
        fmt = ExportFormat(fmt) if isinstance(fmt, str) else fmt
        result: str | Path
        if fmt is ExportFormat.JSON:
            text = json.dumps(
                {
                    "kind": dataset.kind.value,
                    "columns": dataset.columns,
                    "metadata": dataset.metadata,
                    "rows": dataset.rows,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
            result = self._write_or_return(text, path, suffix=".json")
        elif fmt is ExportFormat.CSV:
            text = self._to_csv(self._flatten_rows(dataset.rows))
            result = self._write_or_return(text, path, suffix=".csv")
        elif fmt is ExportFormat.PARQUET:
            result = self._export_parquet(
                self._flatten_rows(dataset.rows), path
            )
        else:
            raise ExportError(f"dataset export unsupported for {fmt}")

        self.metrics.incr("dataset_exports")
        self.events.emit(
            DatasetGenerated(
                dataset.kind.value,
                rows=len(dataset.rows),
                format=fmt.value,
            )
        )
        self.events.emit(
            ExecutionExported(attributes={"dataset_kind": dataset.kind.value})
        )
        return result

    def _export_parquet(
        self, rows: list[dict[str, Any]], path: str | Path | None
    ) -> Path:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ExportError(
                "pyarrow required for parquet export; pip install pyarrow"
            ) from exc
        if path is None:
            raise ExportError("parquet export requires an output path")
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            table = pa.table({})
        else:
            # normalize keys
            keys = sorted({k for row in rows for k in row})
            columns = {k: [row.get(k) for row in rows] for k in keys}
            table = pa.table(columns)
        pq.write_table(table, out)
        self.metrics.incr("dataset_exports")
        return out

    @staticmethod
    def _flat_record(record: ExecutionRecord) -> dict[str, Any]:
        return {
            "execution_id": record.execution_id,
            "workflow_id": record.workflow_id,
            "request_id": record.request_id or "",
            "session_id": record.session_id or "",
            "timestamp": record.timestamp.isoformat(),
            "success": record.success,
            "latency": record.latency,
            "queue_latency": record.queue_latency,
            "execution_latency": record.execution_latency,
            "estimated_cost": record.estimated_cost,
            "estimated_energy": record.estimated_energy,
            "quality": record.quality_score.score,
            "retry_count": record.retry_count,
            "models_used": "|".join(record.models_used),
            "backends_used": "|".join(record.backends_used),
            "agents": "|".join(a.agent_id for a in record.agent_assignments),
            "tags": "|".join(record.tags),
            "content_hash": record.content_hash or "",
        }

    @staticmethod
    def _otel_span_like(record: ExecutionRecord) -> dict[str, Any]:
        return {
            "name": "nexus.swarm.experience.execution",
            "trace_id": record.trace_reference,
            "attributes": {
                "nexus.swarm.experience.execution_id": record.execution_id,
                "nexus.swarm.experience.workflow_id": record.workflow_id,
                "nexus.swarm.experience.success": record.success,
                "nexus.swarm.experience.latency_ms": record.latency,
                "nexus.swarm.experience.cost": record.estimated_cost,
                "nexus.swarm.experience.quality": record.quality_score.score,
                "nexus.swarm.experience.models": list(record.models_used),
                "nexus.swarm.experience.backends": list(record.backends_used),
            },
            "start_time": record.timestamp.isoformat(),
            "duration_ms": record.latency,
        }

    @staticmethod
    def _flatten_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    item[k] = json.dumps(v, sort_keys=True, default=str)
                else:
                    item[k] = v
            flat.append(item)
        return flat

    @staticmethod
    def _to_csv(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        fieldnames: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()

    @staticmethod
    def _write_or_return(
        text: str, path: str | Path | None, *, suffix: str
    ) -> str | Path:
        if path is None:
            return text
        out = Path(path)
        if out.suffix == "":
            out = out.with_suffix(suffix)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        return out
