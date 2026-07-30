"""Postgres MCP server — FastMCP + psycopg (read-only vs write paths).

Auth:
  DATABASE_URL_READONLY — required for query/list/describe/explain (fail closed if unset)
  DATABASE_URL — write tools (execute/insert_row/create_index)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from fastmcp import FastMCP
from psycopg import Error as PsycopgError
from psycopg.rows import dict_row

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from neuroswarm_arm.runtime.router.mcp_sql_safety import (  # noqa: E402
    SqlSafetyError,
    assert_single_readonly_statement,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_URL_READONLY = os.environ.get("DATABASE_URL_READONLY")  # no fallback to write DSN
MAX_ROWS = 500
STATEMENT_TIMEOUT_MS = int(os.environ.get("NSA_MCP_PG_STATEMENT_TIMEOUT_MS", "15000"))
MAX_RESULT_BYTES = int(os.environ.get("NSA_MCP_PG_MAX_RESULT_BYTES", str(256 * 1024)))

mcp = FastMCP("postgres")


def _map_db_error(exc: Exception) -> ValueError:
    msg = str(exc)
    lower = msg.lower()
    if "password authentication failed" in lower or "authentication failed" in lower:
        return ValueError(
            "Postgres auth failed. Check DATABASE_URL user/password and that the role exists."
        )
    if "does not exist" in lower and "database" in lower:
        return ValueError("Database not found. Check the database name in DATABASE_URL.")
    if "permission denied" in lower or "insufficientprivilege" in lower.replace(" ", ""):
        return ValueError(
            "Permission denied. Grant SELECT (or needed privileges) to the DATABASE_URL role."
        )
    if "could not connect" in lower or "connection refused" in lower or "timeout" in lower:
        return ValueError(
            f"Could not connect to Postgres. Check host/port in DATABASE_URL and network access. ({msg})"
        )
    if "too many connections" in lower:
        return ValueError("Postgres connection limit hit. Close idle clients and retry.")
    if "read-only" in lower or "cannot execute" in lower:
        return ValueError(f"Read-only transaction rejected write: {msg}")
    return ValueError(f"Postgres error: {msg}")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    return str(value)


def _require_readonly_dsn() -> str:
    dsn = (DATABASE_URL_READONLY or "").strip()
    if not dsn:
        raise ValueError(
            "DATABASE_URL_READONLY is required for read-only tools. "
            "Set a non-writing role DSN; do not rely on DATABASE_URL for query/list/describe/explain."
        )
    return dsn


def _cap_result(payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload, default=str)
    if len(raw.encode("utf-8")) <= MAX_RESULT_BYTES:
        return payload
    rows = list(payload.get("rows") or [])
    while rows and len(json.dumps({**payload, "rows": rows}, default=str).encode("utf-8")) > MAX_RESULT_BYTES:
        if len(rows) <= 1:
            rows = []
            break
        rows = rows[: len(rows) // 2]
    out = dict(payload)
    out["rows"] = rows
    out["rowcount"] = len(rows)
    out["truncated"] = True
    out["byte_truncated"] = True
    return out


def _execute(
    sql: str,
    params: tuple[Any, ...] | None = None,
    *,
    dsn: str | None,
    read_only: bool,
) -> dict[str, Any]:
    if not dsn:
        raise ValueError(
            "DATABASE_URL is not set. Export postgresql://user:pass@host:5432/dbname before querying."
        )
    if not sql or not sql.strip():
        raise ValueError("sql is required")
    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if read_only:
                    cur.execute("SET default_transaction_read_only = on")
                    cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(f"SET statement_timeout = {int(STATEMENT_TIMEOUT_MS)}")
                if params is None:
                    cur.execute(sql)
                else:
                    cur.execute(sql, params)
                if cur.description is None:
                    if read_only:
                        return {
                            "columns": [],
                            "rows": [],
                            "rowcount": cur.rowcount,
                            "status": cur.statusmessage,
                        }
                    conn.commit()
                    return {
                        "columns": [],
                        "rows": [],
                        "rowcount": cur.rowcount,
                        "status": cur.statusmessage,
                    }
                rows = cur.fetchmany(MAX_ROWS + 1)
                truncated = len(rows) > MAX_ROWS
                if truncated:
                    rows = rows[:MAX_ROWS]
                columns = [d.name for d in cur.description]
                serializable = [{k: _jsonable(v) for k, v in row.items()} for row in rows]
                payload = {
                    "columns": columns,
                    "rows": serializable,
                    "rowcount": len(serializable),
                    "truncated": truncated,
                }
                if read_only:
                    return _cap_result(payload)
                return payload
    except PsycopgError as exc:
        raise _map_db_error(exc) from None
    except OSError as exc:
        raise _map_db_error(exc) from None


async def _run_ro(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any]:
    safe = assert_single_readonly_statement(sql)
    dsn = _require_readonly_dsn()
    return await asyncio.to_thread(_execute, safe, params, dsn=dsn, read_only=True)


async def _run_rw(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(
        _execute, sql, params, dsn=DATABASE_URL, read_only=False
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def query(sql: str) -> dict[str, Any]:
    """Execute a single read-only SQL statement (SELECT/WITH/EXPLAIN/SHOW/VALUES)."""
    try:
        return await _run_ro(sql)
    except SqlSafetyError as exc:
        raise ValueError(str(exc)) from None


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def execute(sql: str) -> dict[str, Any]:
    """Execute a write/DDL statement (requires destructive approval at gateway)."""
    return await _run_rw(sql)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_tables(schema: str = "public") -> dict[str, Any]:
    """List tables in a schema."""
    sql = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    return await _run_ro(sql, (schema,))


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def describe_table(table: str, schema: str = "public") -> dict[str, Any]:
    """Describe columns for a table."""
    if not table:
        raise ValueError("table is required")
    sql = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """
    return await _run_ro(sql, (schema, table))


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def explain(sql: str) -> dict[str, Any]:
    """Run EXPLAIN on a read-only SQL statement."""
    try:
        safe = assert_single_readonly_statement(sql)
    except SqlSafetyError as exc:
        raise ValueError(str(exc)) from None
    return await _run_ro(f"EXPLAIN {safe}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def insert_row(table: str, values: dict[str, Any], schema: str = "public") -> dict[str, Any]:
    """Insert a single row (destructive; approval-gated at gateway)."""
    if not table or not values:
        raise ValueError("table and values are required")
    cols = list(values.keys())
    for ident in [schema, table, *cols]:
        if not str(ident).replace("_", "").isalnum():
            raise ValueError(f"unsafe identifier: {ident}")
    col_sql = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f'INSERT INTO "{schema}"."{table}" ({col_sql}) VALUES ({placeholders}) RETURNING *'
    return await _run_rw(sql, tuple(values[c] for c in cols))


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def create_index(
    table: str,
    columns: list[str],
    name: str | None = None,
    unique: bool = False,
    schema: str = "public",
) -> dict[str, Any]:
    """Create a btree index (destructive DDL; approval-gated)."""
    if not table or not columns:
        raise ValueError("table and columns are required")
    for ident in [schema, table, *(columns), name or "idx"]:
        if ident and not str(ident).replace("_", "").isalnum():
            raise ValueError(f"unsafe identifier: {ident}")
    idx = name or f"idx_{table}_{'_'.join(columns)}"
    uniq = "UNIQUE " if unique else ""
    col_sql = ", ".join(f'"{c}"' for c in columns)
    sql = f'CREATE {uniq}INDEX IF NOT EXISTS "{idx}" ON "{schema}"."{table}" ({col_sql})'
    return await _run_rw(sql)


if __name__ == "__main__":
    mcp.run()
