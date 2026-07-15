"""RCIS persistence — SQLite / DuckDB / Postgres / Parquet / JSON."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping

from .schemas import CostPrediction, RuntimeCostReport, utcnow


class BackendUnavailableError(RuntimeError):
    pass


class JsonPersistence:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._reports = self.root / "reports.jsonl"
        self._predictions = self.root / "predictions.jsonl"

    def write_prediction(self, prediction: CostPrediction) -> None:
        self._append(
            self._predictions,
            prediction.model_dump(mode="json", exclude_computed_fields=True),
        )

    def write_report(self, report: RuntimeCostReport) -> None:
        self._append(
            self._reports,
            report.model_dump(mode="json", exclude_computed_fields=True),
        )

    def query_reports(
        self,
        *,
        tenant_id: str = "",
        backend: str = "",
        quantization: str = "",
        model_tier: str = "",
        agent_id: str = "",
        workflow_id: str = "",
        limit: int = 200,
    ) -> list[RuntimeCostReport]:
        rows = self._read_jsonl(self._reports)
        out: list[RuntimeCostReport] = []
        for obj in rows:
            if tenant_id and str(obj.get("tenant_id", "")) != tenant_id:
                continue
            if backend and str(obj.get("backend", "")) != backend:
                continue
            if quantization and str(obj.get("quantization", "")) != quantization:
                continue
            if model_tier and str(obj.get("model_tier", "")) != model_tier:
                continue
            if agent_id and str(obj.get("agent_id", "")) != agent_id:
                continue
            if workflow_id and str(obj.get("workflow_id", "")) != workflow_id:
                continue
            try:
                out.append(RuntimeCostReport.model_validate(obj))
            except Exception:
                continue
        return out[-limit:]

    def query_predictions(self, *, request_id: str = "", limit: int = 100) -> list[CostPrediction]:
        rows = self._read_jsonl(self._predictions)
        out: list[CostPrediction] = []
        for obj in rows:
            if request_id and str(obj.get("request_id", "")) != request_id:
                continue
            try:
                out.append(CostPrediction.model_validate(obj))
            except Exception:
                continue
        return out[-limit:]

    def _append(self, path: Path, payload: Mapping[str, Any]) -> None:
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, default=str) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


class SqlitePersistence:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "rcis_history.sqlite3"
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS predictions (
                        prediction_id TEXT PRIMARY KEY,
                        request_id TEXT,
                        execution_id TEXT,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reports (
                        report_id TEXT PRIMARY KEY,
                        request_id TEXT,
                        execution_id TEXT,
                        tenant_id TEXT,
                        backend TEXT,
                        quantization TEXT,
                        model_tier TEXT,
                        agent_id TEXT,
                        workflow_id TEXT,
                        estimated_dollars REAL,
                        latency_ms REAL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reports_backend ON reports(backend)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reports_quant ON reports(quantization)"
                )
                conn.commit()
            finally:
                conn.close()

    def write_prediction(self, prediction: CostPrediction) -> None:
        payload = json.dumps(
            prediction.model_dump(mode="json", exclude_computed_fields=True),
            default=str,
        )
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO predictions
                    (prediction_id, request_id, execution_id, payload, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        prediction.prediction_id,
                        prediction.request_id,
                        prediction.execution_id,
                        payload,
                        prediction.created_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def write_report(self, report: RuntimeCostReport) -> None:
        payload = json.dumps(
            report.model_dump(mode="json", exclude_computed_fields=True),
            default=str,
        )
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO reports
                    (report_id, request_id, execution_id, tenant_id, backend, quantization,
                     model_tier, agent_id, workflow_id, estimated_dollars, latency_ms,
                     payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.report_id,
                        report.request_id,
                        report.execution_id,
                        report.tenant_id,
                        report.backend,
                        report.quantization,
                        report.model_tier,
                        report.agent_id,
                        report.workflow_id,
                        report.estimated_dollars,
                        report.latency_ms,
                        payload,
                        report.created_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def query_reports(
        self,
        *,
        tenant_id: str = "",
        backend: str = "",
        quantization: str = "",
        model_tier: str = "",
        agent_id: str = "",
        workflow_id: str = "",
        limit: int = 200,
    ) -> list[RuntimeCostReport]:
        clauses: list[str] = []
        args: list[Any] = []
        if tenant_id:
            clauses.append("tenant_id = ?")
            args.append(tenant_id)
        if backend:
            clauses.append("backend = ?")
            args.append(backend)
        if quantization:
            clauses.append("quantization = ?")
            args.append(quantization)
        if model_tier:
            clauses.append("model_tier = ?")
            args.append(model_tier)
        if agent_id:
            clauses.append("agent_id = ?")
            args.append(agent_id)
        if workflow_id:
            clauses.append("workflow_id = ?")
            args.append(workflow_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT payload FROM reports{where} ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, args).fetchall()
            finally:
                conn.close()
        out: list[RuntimeCostReport] = []
        for row in rows:
            try:
                out.append(RuntimeCostReport.model_validate(json.loads(row["payload"])))
            except Exception:
                continue
        out.reverse()
        return out

    def query_predictions(self, *, request_id: str = "", limit: int = 100) -> list[CostPrediction]:
        if request_id:
            sql = (
                "SELECT payload FROM predictions WHERE request_id = ? "
                "ORDER BY created_at DESC LIMIT ?"
            )
            args: list[Any] = [request_id, int(limit)]
        else:
            sql = "SELECT payload FROM predictions ORDER BY created_at DESC LIMIT ?"
            args = [int(limit)]
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, args).fetchall()
            finally:
                conn.close()
        out: list[CostPrediction] = []
        for row in rows:
            try:
                out.append(CostPrediction.model_validate(json.loads(row["payload"])))
            except Exception:
                continue
        out.reverse()
        return out


class DuckDBPersistence:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._fallback = SqlitePersistence(self.root)
        try:
            import duckdb  # type: ignore

            self._duck = duckdb
            self.db_path = self.root / "rcis_history.duckdb"
            self._ready = True
            self._init()
        except Exception as exc:
            self._ready = False
            self._error = str(exc)

    def _init(self) -> None:
        con = self._duck.connect(str(self.db_path))
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    report_id VARCHAR PRIMARY KEY,
                    created_at VARCHAR,
                    payload VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    prediction_id VARCHAR PRIMARY KEY,
                    created_at VARCHAR,
                    payload VARCHAR
                )
                """
            )
        finally:
            con.close()

    def write_prediction(self, prediction: CostPrediction) -> None:
        if not self._ready:
            self._fallback.write_prediction(prediction)
            return
        payload = json.dumps(
            prediction.model_dump(mode="json", exclude_computed_fields=True),
            default=str,
        )
        con = self._duck.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT OR REPLACE INTO predictions VALUES (?, ?, ?)",
                [prediction.prediction_id, prediction.created_at, payload],
            )
        finally:
            con.close()

    def write_report(self, report: RuntimeCostReport) -> None:
        if not self._ready:
            self._fallback.write_report(report)
            return
        payload = json.dumps(
            report.model_dump(mode="json", exclude_computed_fields=True),
            default=str,
        )
        con = self._duck.connect(str(self.db_path))
        try:
            con.execute(
                "INSERT OR REPLACE INTO reports VALUES (?, ?, ?)",
                [report.report_id, report.created_at, payload],
            )
        finally:
            con.close()

    def query_reports(self, **kwargs: Any) -> list[RuntimeCostReport]:
        if not self._ready:
            return self._fallback.query_reports(**kwargs)
        limit = int(kwargs.get("limit", 200))
        con = self._duck.connect(str(self.db_path))
        try:
            rows = con.execute(
                "SELECT payload FROM reports ORDER BY created_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        finally:
            con.close()
        out: list[RuntimeCostReport] = []
        for (payload,) in rows:
            try:
                report = RuntimeCostReport.model_validate(json.loads(payload))
            except Exception:
                continue
            if kwargs.get("backend") and report.backend != kwargs["backend"]:
                continue
            if kwargs.get("quantization") and report.quantization != kwargs["quantization"]:
                continue
            if kwargs.get("model_tier") and report.model_tier != kwargs["model_tier"]:
                continue
            if kwargs.get("tenant_id") and report.tenant_id != kwargs["tenant_id"]:
                continue
            if kwargs.get("agent_id") and report.agent_id != kwargs["agent_id"]:
                continue
            if kwargs.get("workflow_id") and report.workflow_id != kwargs["workflow_id"]:
                continue
            out.append(report)
        out.reverse()
        return out

    def query_predictions(self, *, request_id: str = "", limit: int = 100) -> list[CostPrediction]:
        if not self._ready:
            return self._fallback.query_predictions(request_id=request_id, limit=limit)
        con = self._duck.connect(str(self.db_path))
        try:
            rows = con.execute(
                "SELECT payload FROM predictions ORDER BY created_at DESC LIMIT ?",
                [int(limit)],
            ).fetchall()
        finally:
            con.close()
        out: list[CostPrediction] = []
        for (payload,) in rows:
            try:
                pred = CostPrediction.model_validate(json.loads(payload))
            except Exception:
                continue
            if request_id and pred.request_id != request_id:
                continue
            out.append(pred)
        out.reverse()
        return out


class PostgresPersistence:
    """Optional Postgres backend; falls back to SQLite if driver/DSN unavailable."""

    def __init__(self, root: Path, *, dsn: str = "") -> None:
        self.root = Path(root)
        self.dsn = dsn or ""
        self._fallback = SqlitePersistence(self.root)
        self._conn = None
        if self.dsn:
            try:
                import psycopg  # type: ignore

                self._conn = psycopg.connect(self.dsn)
                self._init()
            except Exception:
                self._conn = None

    def _init(self) -> None:
        assert self._conn is not None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rcis_reports (
                    report_id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rcis_predictions (
                    prediction_id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        self._conn.commit()

    def write_prediction(self, prediction: CostPrediction) -> None:
        if self._conn is None:
            self._fallback.write_prediction(prediction)
            return
        payload = prediction.model_dump(mode="json")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rcis_predictions (prediction_id, payload)
                VALUES (%s, %s)
                ON CONFLICT (prediction_id) DO UPDATE SET payload = EXCLUDED.payload
                """,
                (prediction.prediction_id, json.dumps(payload)),
            )
        self._conn.commit()

    def write_report(self, report: RuntimeCostReport) -> None:
        if self._conn is None:
            self._fallback.write_report(report)
            return
        payload = report.model_dump(mode="json")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rcis_reports (report_id, payload)
                VALUES (%s, %s)
                ON CONFLICT (report_id) DO UPDATE SET payload = EXCLUDED.payload
                """,
                (report.report_id, json.dumps(payload)),
            )
        self._conn.commit()

    def query_reports(self, **kwargs: Any) -> list[RuntimeCostReport]:
        if self._conn is None:
            return self._fallback.query_reports(**kwargs)
        limit = int(kwargs.get("limit", 200))
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM rcis_reports ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        out: list[RuntimeCostReport] = []
        for (payload,) in rows:
            obj = payload if isinstance(payload, dict) else json.loads(payload)
            try:
                report = RuntimeCostReport.model_validate(obj)
            except Exception:
                continue
            if kwargs.get("backend") and report.backend != kwargs["backend"]:
                continue
            out.append(report)
        out.reverse()
        return out

    def query_predictions(self, *, request_id: str = "", limit: int = 100) -> list[CostPrediction]:
        if self._conn is None:
            return self._fallback.query_predictions(request_id=request_id, limit=limit)
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM rcis_predictions ORDER BY created_at DESC LIMIT %s",
                (int(limit),),
            )
            rows = cur.fetchall()
        out: list[CostPrediction] = []
        for (payload,) in rows:
            obj = payload if isinstance(payload, dict) else json.loads(payload)
            try:
                pred = CostPrediction.model_validate(obj)
            except Exception:
                continue
            if request_id and pred.request_id != request_id:
                continue
            out.append(pred)
        out.reverse()
        return out


class ParquetPersistence:
    """Parquet append via pandas/pyarrow when available; else JSONL fallback."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._fallback = JsonPersistence(self.root)
        self._reports_path = self.root / "reports.parquet"
        self._preds_path = self.root / "predictions.parquet"

    def write_prediction(self, prediction: CostPrediction) -> None:
        try:
            import pandas as pd  # type: ignore

            row = prediction.model_dump(mode="json")
            df = pd.DataFrame([{"payload": json.dumps(row, default=str), "ts": utcnow().isoformat()}])
            if self._preds_path.is_file():
                existing = pd.read_parquet(self._preds_path)
                df = pd.concat([existing, df], ignore_index=True)
            df.to_parquet(self._preds_path, index=False)
        except Exception:
            self._fallback.write_prediction(prediction)

    def write_report(self, report: RuntimeCostReport) -> None:
        try:
            import pandas as pd  # type: ignore

            row = report.model_dump(mode="json")
            df = pd.DataFrame([{"payload": json.dumps(row, default=str), "ts": utcnow().isoformat()}])
            if self._reports_path.is_file():
                existing = pd.read_parquet(self._reports_path)
                df = pd.concat([existing, df], ignore_index=True)
            df.to_parquet(self._reports_path, index=False)
        except Exception:
            self._fallback.write_report(report)

    def query_reports(self, **kwargs: Any) -> list[RuntimeCostReport]:
        try:
            import pandas as pd  # type: ignore

            if not self._reports_path.is_file():
                return []
            df = pd.read_parquet(self._reports_path)
            limit = int(kwargs.get("limit", 200))
            out: list[RuntimeCostReport] = []
            for payload in df["payload"].tolist()[-limit:]:
                try:
                    report = RuntimeCostReport.model_validate(json.loads(payload))
                except Exception:
                    continue
                if kwargs.get("backend") and report.backend != kwargs["backend"]:
                    continue
                if kwargs.get("quantization") and report.quantization != kwargs["quantization"]:
                    continue
                out.append(report)
            return out
        except Exception:
            return self._fallback.query_reports(**kwargs)

    def query_predictions(self, *, request_id: str = "", limit: int = 100) -> list[CostPrediction]:
        try:
            import pandas as pd  # type: ignore

            if not self._preds_path.is_file():
                return []
            df = pd.read_parquet(self._preds_path)
            out: list[CostPrediction] = []
            for payload in df["payload"].tolist()[-int(limit) :]:
                try:
                    pred = CostPrediction.model_validate(json.loads(payload))
                except Exception:
                    continue
                if request_id and pred.request_id != request_id:
                    continue
                out.append(pred)
            return out
        except Exception:
            return self._fallback.query_predictions(request_id=request_id, limit=limit)


def build_persistence(name: str, root: Path, **kwargs: Any) -> Any:
    key = (name or "sqlite").lower()
    if key in {"json", "jsonl"}:
        return JsonPersistence(root)
    if key == "duckdb":
        return DuckDBPersistence(root)
    if key in {"postgres", "postgresql"}:
        return PostgresPersistence(root, dsn=str(kwargs.get("dsn", "")))
    if key == "parquet":
        return ParquetPersistence(root)
    return SqlitePersistence(root)
