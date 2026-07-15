"""Profile exporters — JSON / Parquet / SQLite / DuckDB / OTLP / Prometheus text."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .schemas import RuntimeProfile

logger = logging.getLogger(__name__)


class JsonProfileExporter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def name(self) -> str:
        return "json"

    def export(self, profile: RuntimeProfile) -> None:
        path = self.root / f"{profile.profile_id}.json"
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        # append to jsonl index
        index = self.root / "profiles.jsonl"
        with index.open("a", encoding="utf-8") as fh:
            fh.write(profile.model_dump_json() + "\n")


class PrometheusTextExporter:
    """Writes last prometheus scrape snapshot alongside profiles (optional file sink)."""

    def __init__(self, root: Path, telemetry: Any) -> None:
        self.root = root
        self.telemetry = telemetry
        self.root.mkdir(parents=True, exist_ok=True)

    def name(self) -> str:
        return "prometheus"

    def export(self, profile: RuntimeProfile) -> None:
        del profile
        try:
            text = self.telemetry.export_prometheus()
            (self.root / "profile_metrics.prom").write_text(text, encoding="utf-8")
        except Exception as exc:
            logger.warning("rpf prometheus file export failed: %s", exc)


class SqliteProfileExporter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "profiles.sqlite"
        self._init_db()

    def name(self) -> str:
        return "sqlite"

    def _init_db(self) -> None:
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id TEXT PRIMARY KEY,
                    request_id TEXT,
                    execution_id TEXT,
                    profiler_used TEXT,
                    created_at TEXT,
                    payload TEXT
                )
                """
            )

    def export(self, profile: RuntimeProfile) -> None:
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
                (
                    profile.profile_id,
                    profile.request_id,
                    profile.execution_id,
                    profile.profiler_used,
                    profile.created_at,
                    profile.model_dump_json(),
                ),
            )


class DuckDBProfileExporter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "profiles.duckdb"
        self._duck: Any | None = None
        try:
            import duckdb  # type: ignore

            self._duck = duckdb
            con = duckdb.connect(str(self.db))
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id VARCHAR,
                    request_id VARCHAR,
                    execution_id VARCHAR,
                    profiler_used VARCHAR,
                    created_at VARCHAR,
                    payload VARCHAR
                )
                """
            )
            con.close()
        except Exception as exc:
            logger.info("rpf duckdb unavailable, will degrade: %s", exc)
            self._duck = None

    def name(self) -> str:
        return "duckdb"

    def export(self, profile: RuntimeProfile) -> None:
        if self._duck is None:
            JsonProfileExporter(self.root).export(profile)
            return
        try:
            con = self._duck.connect(str(self.db))
            con.execute(
                "INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
                [
                    profile.profile_id,
                    profile.request_id,
                    profile.execution_id,
                    profile.profiler_used,
                    profile.created_at,
                    profile.model_dump_json(),
                ],
            )
            con.close()
        except Exception as exc:
            logger.warning("rpf duckdb export failed: %s", exc)
            JsonProfileExporter(self.root).export(profile)


class ParquetProfileExporter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._pd: Any | None = None
        try:
            import pandas as pd  # type: ignore

            self._pd = pd
        except Exception:
            self._pd = None

    def name(self) -> str:
        return "parquet"

    def export(self, profile: RuntimeProfile) -> None:
        if self._pd is None:
            JsonProfileExporter(self.root).export(profile)
            return
        try:
            row = {
                "profile_id": profile.profile_id,
                "request_id": profile.request_id,
                "execution_id": profile.execution_id,
                "profiler_used": profile.profiler_used,
                "ipc": profile.hardware.ipc,
                "cpu_percent": profile.cpu.usage_percent,
                "peak_rss": profile.memory.peak_rss_bytes,
                "execution_ms": profile.execution.execution_time_ms,
                "created_at": profile.created_at,
                "payload": profile.model_dump_json(),
            }
            path = self.root / "profiles.parquet"
            df = self._pd.DataFrame([row])
            if path.exists():
                existing = self._pd.read_parquet(path)
                df = self._pd.concat([existing, df], ignore_index=True)
            df.to_parquet(path, index=False)
        except Exception as exc:
            logger.warning("rpf parquet export failed: %s", exc)
            JsonProfileExporter(self.root).export(profile)


class OTLPProfileExporter:
    """Best-effort OTLP span export for profile finalization."""

    def __init__(self) -> None:
        self._tracer = None
        try:
            from opentelemetry import trace  # type: ignore

            self._tracer = trace.get_tracer("nexus.armora.rpf.otlp")
        except Exception:
            self._tracer = None

    def name(self) -> str:
        return "otlp"

    def export(self, profile: RuntimeProfile) -> None:
        if self._tracer is None:
            return
        try:
            with self._tracer.start_as_current_span("rpf.export") as span:
                span.set_attribute("profile_id", profile.profile_id)
                span.set_attribute("profiler", profile.profiler_used)
                span.set_attribute("ipc", float(profile.hardware.ipc))
        except Exception as exc:
            logger.warning("rpf otlp export failed: %s", exc)


class CompositeProfileExporter:
    def __init__(self, exporters: list[Any]) -> None:
        self.exporters = list(exporters)

    def name(self) -> str:
        return "composite"

    def export(self, profile: RuntimeProfile) -> None:
        for exp in self.exporters:
            try:
                exp.export(profile)
            except Exception as exc:
                logger.warning("rpf exporter %s failed: %s", getattr(exp, "name", "?"), exc)


def build_exporter(
    kind: str,
    root: Path,
    *,
    telemetry: Any | None = None,
    otel: bool = False,
) -> Any:
    exporters: list[Any] = []
    primary = (kind or "json").lower()
    if primary == "sqlite":
        exporters.append(SqliteProfileExporter(root))
    elif primary == "duckdb":
        exporters.append(DuckDBProfileExporter(root))
    elif primary == "parquet":
        exporters.append(ParquetProfileExporter(root))
    elif primary == "prometheus" and telemetry is not None:
        exporters.append(PrometheusTextExporter(root, telemetry))
    else:
        exporters.append(JsonProfileExporter(root))
    # Always keep JSON as durable fallback when not already primary
    if primary != "json":
        exporters.append(JsonProfileExporter(root / "json_fallback"))
    if otel or primary == "otlp":
        exporters.append(OTLPProfileExporter())
    if len(exporters) == 1:
        return exporters[0]
    return CompositeProfileExporter(exporters)


class ProfileStore:
    """Simple queryable store over JSONL for feedback repositories."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._jsonl = self.root / "profiles.jsonl"

    def write(self, profile: RuntimeProfile) -> None:
        with self._jsonl.open("a", encoding="utf-8") as fh:
            fh.write(profile.model_dump_json() + "\n")

    def query(self, *, limit: int = 200) -> list[RuntimeProfile]:
        if not self._jsonl.exists():
            return []
        rows: list[RuntimeProfile] = []
        try:
            lines = self._jsonl.read_text(encoding="utf-8").splitlines()
            for line in lines[-limit:]:
                try:
                    rows.append(RuntimeProfile.model_validate(json.loads(line)))
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("rpf store query failed: %s", exc)
        return rows
