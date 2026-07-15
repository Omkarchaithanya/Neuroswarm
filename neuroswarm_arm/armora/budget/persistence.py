"""Persistence backends — SQLite / DuckDB / Postgres / JSON / Parquet."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping

from .schemas import utcnow


class BackendUnavailableError(RuntimeError):
    pass


class JsonlPersistence:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write_envelope(self, envelope_id: str, payload: Mapping[str, Any]) -> None:
        self._append("envelopes.jsonl", {"envelope_id": envelope_id, **dict(payload)})

    def write_report(self, envelope_id: str, report_type: str, payload: Mapping[str, Any]) -> None:
        self._append(
            "reports.jsonl",
            {
                "envelope_id": envelope_id,
                "report_type": report_type,
                "ts": utcnow().isoformat(),
                **dict(payload),
            },
        )

    def query_history(self, *, tenant_id: str = "", limit: int = 100) -> list[Mapping[str, Any]]:
        path = self.root / "envelopes.jsonl"
        if not path.is_file():
            return []
        rows: list[Mapping[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if tenant_id and str(obj.get("tenant_id", "")) != tenant_id:
                    continue
                rows.append(obj)
        return rows[-limit:]

    def _append(self, name: str, payload: Mapping[str, Any]) -> None:
        path = self.root / name
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, default=str) + "\n")


class SqlitePersistence:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "budget_history.sqlite3"
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
                    CREATE TABLE IF NOT EXISTS envelopes (
                        envelope_id TEXT PRIMARY KEY,
                        tenant_id TEXT,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        envelope_id TEXT NOT NULL,
                        report_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def write_envelope(self, envelope_id: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO envelopes(envelope_id, tenant_id, payload, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        envelope_id,
                        str(payload.get("tenant_id", "")),
                        json.dumps(dict(payload), default=str),
                        utcnow().isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def write_report(self, envelope_id: str, report_type: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO reports(envelope_id, report_type, payload, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        envelope_id,
                        report_type,
                        json.dumps(dict(payload), default=str),
                        utcnow().isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def query_history(self, *, tenant_id: str = "", limit: int = 100) -> list[Mapping[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                if tenant_id:
                    cur = conn.execute(
                        """
                        SELECT payload FROM envelopes
                        WHERE tenant_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (tenant_id, int(limit)),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT payload FROM envelopes
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (int(limit),),
                    )
                out: list[Mapping[str, Any]] = []
                for row in cur.fetchall():
                    out.append(json.loads(row["payload"]))
                return out
            finally:
                conn.close()


class DuckDbPersistence:
    def __init__(self, root: Path) -> None:
        try:
            import duckdb  # type: ignore
        except ImportError as exc:
            raise BackendUnavailableError(
                "DuckDB backend selected but duckdb is not installed"
            ) from exc
        self._duckdb = duckdb
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "budget_history.duckdb"
        self._lock = threading.Lock()
        self._json = JsonlPersistence(self.root / "duckdb_mirror")
        with self._lock:
            con = self._duckdb.connect(str(self.db_path))
            try:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS envelopes(envelope_id VARCHAR, tenant_id VARCHAR, payload VARCHAR, created_at VARCHAR)"
                )
                con.execute(
                    "CREATE TABLE IF NOT EXISTS reports(envelope_id VARCHAR, report_type VARCHAR, payload VARCHAR, created_at VARCHAR)"
                )
            finally:
                con.close()

    def write_envelope(self, envelope_id: str, payload: Mapping[str, Any]) -> None:
        self._json.write_envelope(envelope_id, payload)
        with self._lock:
            con = self._duckdb.connect(str(self.db_path))
            try:
                con.execute(
                    "INSERT INTO envelopes VALUES (?, ?, ?, ?)",
                    [
                        envelope_id,
                        str(payload.get("tenant_id", "")),
                        json.dumps(dict(payload), default=str),
                        utcnow().isoformat(),
                    ],
                )
            finally:
                con.close()

    def write_report(self, envelope_id: str, report_type: str, payload: Mapping[str, Any]) -> None:
        self._json.write_report(envelope_id, report_type, payload)
        with self._lock:
            con = self._duckdb.connect(str(self.db_path))
            try:
                con.execute(
                    "INSERT INTO reports VALUES (?, ?, ?, ?)",
                    [
                        envelope_id,
                        report_type,
                        json.dumps(dict(payload), default=str),
                        utcnow().isoformat(),
                    ],
                )
            finally:
                con.close()

    def query_history(self, *, tenant_id: str = "", limit: int = 100) -> list[Mapping[str, Any]]:
        return self._json.query_history(tenant_id=tenant_id, limit=limit)


class PostgresPersistence:
    def __init__(self, dsn: str, root: Path) -> None:
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise BackendUnavailableError(
                "Postgres backend selected but psycopg is not installed"
            ) from exc
        self._psycopg = psycopg
        self.dsn = dsn
        self._fallback = JsonlPersistence(Path(root) / "postgres_fallback")
        self._init()

    def _init(self) -> None:
        with self._psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS budget_envelopes (
                        envelope_id TEXT PRIMARY KEY,
                        tenant_id TEXT,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS budget_reports (
                        id BIGSERIAL PRIMARY KEY,
                        envelope_id TEXT NOT NULL,
                        report_type TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()

    def write_envelope(self, envelope_id: str, payload: Mapping[str, Any]) -> None:
        try:
            with self._psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO budget_envelopes(envelope_id, tenant_id, payload)
                        VALUES (%s, %s, %s::jsonb)
                        ON CONFLICT (envelope_id) DO UPDATE
                        SET payload = EXCLUDED.payload, tenant_id = EXCLUDED.tenant_id
                        """,
                        (envelope_id, str(payload.get("tenant_id", "")), json.dumps(dict(payload), default=str)),
                    )
                conn.commit()
        except Exception:
            self._fallback.write_envelope(envelope_id, payload)
            raise

    def write_report(self, envelope_id: str, report_type: str, payload: Mapping[str, Any]) -> None:
        try:
            with self._psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO budget_reports(envelope_id, report_type, payload)
                        VALUES (%s, %s, %s::jsonb)
                        """,
                        (envelope_id, report_type, json.dumps(dict(payload), default=str)),
                    )
                conn.commit()
        except Exception:
            self._fallback.write_report(envelope_id, report_type, payload)
            raise

    def query_history(self, *, tenant_id: str = "", limit: int = 100) -> list[Mapping[str, Any]]:
        with self._psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if tenant_id:
                    cur.execute(
                        """
                        SELECT payload FROM budget_envelopes
                        WHERE tenant_id = %s
                        ORDER BY created_at DESC LIMIT %s
                        """,
                        (tenant_id, int(limit)),
                    )
                else:
                    cur.execute(
                        """
                        SELECT payload FROM budget_envelopes
                        ORDER BY created_at DESC LIMIT %s
                        """,
                        (int(limit),),
                    )
                rows = cur.fetchall()
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]


class ParquetPersistence:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._json = JsonlPersistence(self.root)
        self._lock = threading.Lock()

    def write_envelope(self, envelope_id: str, payload: Mapping[str, Any]) -> None:
        self._json.write_envelope(envelope_id, payload)
        self._flush_parquet("envelopes")

    def write_report(self, envelope_id: str, report_type: str, payload: Mapping[str, Any]) -> None:
        self._json.write_report(envelope_id, report_type, payload)
        self._flush_parquet("reports")

    def query_history(self, *, tenant_id: str = "", limit: int = 100) -> list[Mapping[str, Any]]:
        return self._json.query_history(tenant_id=tenant_id, limit=limit)

    def _flush_parquet(self, kind: str) -> None:
        try:
            import pyarrow as pa  # type: ignore
            import pyarrow.parquet as pq  # type: ignore
        except ImportError as exc:
            raise BackendUnavailableError(
                "Parquet backend selected but pyarrow is not installed"
            ) from exc
        src = self.root / f"{kind}.jsonl"
        if not src.is_file():
            return
        rows = []
        with src.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        if not rows:
            return
        table = pa.Table.from_pylist(rows)
        out = self.root / f"{kind}.parquet"
        with self._lock:
            pq.write_table(table, out)


def build_persistence(name: str, root: Path, *, postgres_dsn: str = "") -> Any:
    key = (name or "sqlite").strip().lower()
    if key == "sqlite":
        return SqlitePersistence(root)
    if key == "json" or key == "jsonl":
        return JsonlPersistence(root)
    if key == "duckdb":
        return DuckDbPersistence(root)
    if key == "postgres":
        import os

        dsn = postgres_dsn or os.getenv("NSA_BUDGET_POSTGRES_DSN", "")
        if not dsn:
            raise BackendUnavailableError("NSA_BUDGET_POSTGRES_DSN required for postgres backend")
        return PostgresPersistence(dsn, root)
    if key == "parquet":
        return ParquetPersistence(root)
    raise BackendUnavailableError(f"unknown persistence backend: {name}")
