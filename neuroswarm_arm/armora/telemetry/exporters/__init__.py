"""ROF exporters — OTLP, Prometheus, Jaeger/Tempo/Zipkin presets, JSON, SQLite, DuckDB."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..config import ROFRuntimeConfig
from ..plugins import register_exporter
from ..schemas import LogRecord, MetricSample, RuntimeEvent, SpanRecord

logger = logging.getLogger(__name__)


class _BaseExporter:
    name = "base"

    def export_spans(self, spans: list[SpanRecord]) -> int:
        return 0

    def export_metrics(self, samples: list[MetricSample]) -> int:
        return 0

    def export_logs(self, records: list[LogRecord]) -> int:
        return 0

    def sink_event(self, event: RuntimeEvent) -> None:
        return None

    def export_prometheus(self) -> str:
        return ""

    def shutdown(self, timeout_ms: int = 5000) -> None:
        del timeout_ms


class PrometheusExporter(_BaseExporter):
    """Holds reference to ROF meter for scrape text."""

    name = "prometheus"

    def __init__(self, meter: Any | None = None, **_kw: Any) -> None:
        self.meter = meter

    def bind_meter(self, meter: Any) -> None:
        self.meter = meter

    def export_prometheus(self) -> str:
        if self.meter is None:
            return ""
        return self.meter.export_prometheus()

    def export_metrics(self, samples: list[MetricSample]) -> int:
        if self.meter is None:
            return 0
        for sample in samples:
            self.meter.record_sample(sample)
        return len(samples)


class JSONExporter(_BaseExporter):
    name = "json"

    def __init__(self, config: ROFRuntimeConfig | None = None, **_kw: Any) -> None:
        path = (config.json_path if config else Path("work/rof/telemetry.jsonl")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()

    def _append(self, record_type: str, payload: dict[str, Any]) -> None:
        line = json.dumps({"type": record_type, **payload}, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def export_spans(self, spans: list[SpanRecord]) -> int:
        for span in spans:
            self._append("span", span.model_dump(mode="json"))
        return len(spans)

    def export_metrics(self, samples: list[MetricSample]) -> int:
        for sample in samples:
            self._append("metric", sample.model_dump(mode="json"))
        return len(samples)

    def export_logs(self, records: list[LogRecord]) -> int:
        for record in records:
            self._append("log", record.model_dump(mode="json"))
        return len(records)

    def sink_event(self, event: RuntimeEvent) -> None:
        self._append("event", event.model_dump(mode="json"))


class SQLiteExporter(_BaseExporter):
    name = "sqlite"

    def __init__(self, config: ROFRuntimeConfig | None = None, **_kw: Any) -> None:
        path = (config.sqlite_path if config else Path("work/rof/telemetry.sqlite")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS spans (
                        span_id TEXT PRIMARY KEY,
                        trace_id TEXT,
                        parent_span_id TEXT,
                        name TEXT,
                        start_ns INTEGER,
                        end_ns INTEGER,
                        status TEXT,
                        attributes TEXT
                    );
                    CREATE TABLE IF NOT EXISTS metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        value REAL,
                        metric_type TEXT,
                        labels TEXT,
                        ts TEXT
                    );
                    CREATE TABLE IF NOT EXISTS events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT,
                        severity TEXT,
                        payload TEXT,
                        context TEXT,
                        ts TEXT
                    );
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT,
                        message TEXT,
                        context TEXT,
                        extra TEXT,
                        ts TEXT
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def export_spans(self, spans: list[SpanRecord]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO spans
                    (span_id, trace_id, parent_span_id, name, start_ns, end_ns, status, attributes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            s.span_id,
                            s.trace_id,
                            s.parent_span_id,
                            s.name,
                            s.start_ns,
                            s.end_ns,
                            s.status,
                            json.dumps(dict(s.attributes), default=str),
                        )
                        for s in spans
                    ],
                )
                conn.commit()
            finally:
                conn.close()
        return len(spans)

    def export_metrics(self, samples: list[MetricSample]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                conn.executemany(
                    "INSERT INTO metrics (name, value, metric_type, labels, ts) VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            m.name,
                            m.value,
                            m.metric_type,
                            json.dumps(dict(m.labels), default=str),
                            m.timestamp.isoformat(),
                        )
                        for m in samples
                    ],
                )
                conn.commit()
            finally:
                conn.close()
        return len(samples)

    def export_logs(self, records: list[LogRecord]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                conn.executemany(
                    "INSERT INTO logs (level, message, context, extra, ts) VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            r.level,
                            r.message,
                            json.dumps(dict(r.context), default=str),
                            json.dumps(dict(r.extra), default=str),
                            r.timestamp.isoformat(),
                        )
                        for r in records
                    ],
                )
                conn.commit()
            finally:
                conn.close()
        return len(records)

    def sink_event(self, event: RuntimeEvent) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events
                    (event_id, event_type, severity, payload, context, ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type,
                        event.severity.value,
                        json.dumps(dict(event.payload), default=str),
                        json.dumps(dict(event.context), default=str),
                        event.timestamp.isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()


class DuckDBExporter(_BaseExporter):
    name = "duckdb"

    def __init__(self, config: ROFRuntimeConfig | None = None, **_kw: Any) -> None:
        path = (config.duckdb_path if config else Path("work/rof/telemetry.duckdb")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._duck = None
        try:
            import duckdb  # type: ignore

            self._duck = duckdb
            self._init_db()
        except Exception as exc:
            logger.warning("DuckDB unavailable, exporter disabled: %s", exc)
            self._duck = None

    def _init_db(self) -> None:
        assert self._duck is not None
        with self._lock:
            con = self._duck.connect(str(self.path))
            try:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spans (
                        span_id VARCHAR,
                        trace_id VARCHAR,
                        parent_span_id VARCHAR,
                        name VARCHAR,
                        start_ns BIGINT,
                        end_ns BIGINT,
                        status VARCHAR,
                        attributes VARCHAR
                    )
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        event_id VARCHAR,
                        event_type VARCHAR,
                        severity VARCHAR,
                        payload VARCHAR,
                        context VARCHAR,
                        ts VARCHAR
                    )
                    """
                )
            finally:
                con.close()

    def export_spans(self, spans: list[SpanRecord]) -> int:
        if self._duck is None:
            return 0
        with self._lock:
            con = self._duck.connect(str(self.path))
            try:
                for s in spans:
                    con.execute(
                        "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            s.span_id,
                            s.trace_id,
                            s.parent_span_id,
                            s.name,
                            s.start_ns,
                            s.end_ns,
                            s.status,
                            json.dumps(dict(s.attributes), default=str),
                        ],
                    )
            finally:
                con.close()
        return len(spans)

    def sink_event(self, event: RuntimeEvent) -> None:
        if self._duck is None:
            return
        with self._lock:
            con = self._duck.connect(str(self.path))
            try:
                con.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        event.event_id,
                        event.event_type,
                        event.severity.value,
                        json.dumps(dict(event.payload), default=str),
                        json.dumps(dict(event.context), default=str),
                        event.timestamp.isoformat(),
                    ],
                )
            finally:
                con.close()


class OTLPExporter(_BaseExporter):
    """Configures OTLP HTTP exporters on the global TracerProvider (idempotent)."""

    name = "otlp"

    def __init__(self, config: ROFRuntimeConfig | None = None, **_kw: Any) -> None:
        self.config = config
        self._configured = False
        self._span_exporter = None
        endpoint = (config.otlp_endpoint if config else "") or ""
        if endpoint:
            self._configure(endpoint, insecure=bool(config.otlp_insecure if config else True))

    def _configure(self, endpoint: str, *, insecure: bool = True) -> None:
        del insecure
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create(
                {
                    "service.name": self.config.service_name if self.config else "nexus-arm",
                    "service.version": self.config.service_version if self.config else "0.1.0",
                }
            )
            provider = trace.get_tracer_provider()
            # Only set if not already an SDK provider with processors
            if type(provider).__name__ == "ProxyTracerProvider" or not hasattr(provider, "add_span_processor"):
                provider = TracerProvider(resource=resource)
                trace.set_tracer_provider(provider)
            url = endpoint if endpoint.endswith("/v1/traces") else endpoint.rstrip("/") + "/v1/traces"
            self._span_exporter = OTLPSpanExporter(endpoint=url)
            if hasattr(provider, "add_span_processor"):
                batch = 512
                timeout = 5000
                if self.config:
                    batch = self.config.batch_size
                    timeout = self.config.export_timeout_ms
                provider.add_span_processor(
                    BatchSpanProcessor(
                        self._span_exporter,
                        max_export_batch_size=batch,
                        export_timeout_millis=timeout,
                    )
                )
            self._configured = True
        except Exception as exc:
            logger.warning("OTLP exporter configure failed: %s", exc)
            self._configured = False

    def export_spans(self, spans: list[SpanRecord]) -> int:
        # Spans already exported via BatchSpanProcessor when OTel spans end.
        return len(spans) if self._configured else 0

    def shutdown(self, timeout_ms: int = 5000) -> None:
        del timeout_ms
        try:
            from opentelemetry import trace

            provider = trace.get_tracer_provider()
            if hasattr(provider, "shutdown"):
                provider.shutdown()
        except Exception:
            pass


class JaegerExporter(OTLPExporter):
    """Jaeger via OTLP (Jaeger 1.35+ OTLP receiver)."""

    name = "jaeger"


class TempoExporter(OTLPExporter):
    """Grafana Tempo via OTLP."""

    name = "tempo"


class ZipkinExporter(_BaseExporter):
    """Zipkin JSON exporter (best-effort HTTP POST)."""

    name = "zipkin"

    def __init__(self, config: ROFRuntimeConfig | None = None, **_kw: Any) -> None:
        endpoint = ""
        if config and config.otlp_endpoint:
            # Allow NSA_ROF_OTLP_ENDPOINT to point at Zipkin when exporter=zipkin
            endpoint = config.otlp_endpoint
        self.endpoint = endpoint or "http://127.0.0.1:9411/api/v2/spans"
        self._lock = threading.Lock()

    def export_spans(self, spans: list[SpanRecord]) -> int:
        if not spans:
            return 0
        payload = []
        for s in spans:
            duration = max(0, s.end_ns - s.start_ns)
            payload.append(
                {
                    "traceId": s.trace_id[:32],
                    "id": s.span_id[:16],
                    "parentId": s.parent_span_id[:16] if s.parent_span_id else None,
                    "name": s.name,
                    "timestamp": s.start_ns // 1000,
                    "duration": duration // 1000,
                    "tags": {k: str(v) for k, v in s.attributes.items()},
                }
            )
        try:
            import urllib.request

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                resp.read()
            return len(spans)
        except Exception as exc:
            logger.debug("Zipkin export failed: %s", exc)
            return 0


def register_builtin_exporters() -> None:
    @register_exporter("prometheus")
    def _prom(config: ROFRuntimeConfig | None = None, **kw: Any) -> PrometheusExporter:
        return PrometheusExporter(config=config, **kw)

    @register_exporter("json")
    def _json(config: ROFRuntimeConfig | None = None, **kw: Any) -> JSONExporter:
        return JSONExporter(config=config, **kw)

    @register_exporter("sqlite")
    def _sqlite(config: ROFRuntimeConfig | None = None, **kw: Any) -> SQLiteExporter:
        return SQLiteExporter(config=config, **kw)

    @register_exporter("duckdb")
    def _duckdb(config: ROFRuntimeConfig | None = None, **kw: Any) -> DuckDBExporter:
        return DuckDBExporter(config=config, **kw)

    @register_exporter("otlp")
    def _otlp(config: ROFRuntimeConfig | None = None, **kw: Any) -> OTLPExporter:
        return OTLPExporter(config=config, **kw)

    @register_exporter("jaeger")
    def _jaeger(config: ROFRuntimeConfig | None = None, **kw: Any) -> JaegerExporter:
        return JaegerExporter(config=config, **kw)

    @register_exporter("tempo")
    def _tempo(config: ROFRuntimeConfig | None = None, **kw: Any) -> TempoExporter:
        return TempoExporter(config=config, **kw)

    @register_exporter("zipkin")
    def _zipkin(config: ROFRuntimeConfig | None = None, **kw: Any) -> ZipkinExporter:
        return ZipkinExporter(config=config, **kw)


# Avoid unused import warning for time in some paths
_ = time
