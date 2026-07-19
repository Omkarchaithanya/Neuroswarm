"""Postgres MCP server — REAL implementation (FastMCP + psycopg).

Replaces the fake stub that only echoed its own tool description back.
Auth: export DATABASE_URL=postgresql://user:pass@host:5432/dbname
Use a DB role with SELECT-only grants for read-only access (enforced at the
DB level, not in this server).

Run: python server.py          (stdio, for local MCP clients)
Test: npx @modelcontextprotocol/inspector python server.py
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import psycopg
from fastmcp import FastMCP
from psycopg import Error as PsycopgError
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")
MAX_ROWS = 500

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
            "Permission denied. Grant SELECT (or needed privileges) to the DATABASE_URL role, "
            "or use a role with broader access."
        )
    if "could not connect" in lower or "connection refused" in lower or "timeout" in lower:
        return ValueError(
            f"Could not connect to Postgres. Check host/port in DATABASE_URL and network access. ({msg})"
        )
    if "too many connections" in lower:
        return ValueError("Postgres connection limit hit. Close idle clients and retry.")
    return ValueError(f"Postgres error: {msg}")


def _execute(sql: str) -> dict[str, Any]:
    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL is not set. Export postgresql://user:pass@host:5432/dbname before querying."
        )
    if not sql or not sql.strip():
        raise ValueError("sql is required")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql)
                if cur.description is None:
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
                serializable = []
                for row in rows:
                    serializable.append({k: _jsonable(v) for k, v in row.items()})
                return {
                    "columns": columns,
                    "rows": serializable,
                    "rowcount": len(serializable),
                    "truncated": truncated,
                }
    except PsycopgError as exc:
        raise _map_db_error(exc) from None
    except OSError as exc:
        raise _map_db_error(exc) from None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    return str(value)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def query(sql: str) -> dict[str, Any]:
    """Execute SQL against DATABASE_URL and return columns/rows.

    Prefer a SELECT-only DB role. This server does not block writes in app code.

    Args:
        sql: SQL statement to run
    """
    return await asyncio.to_thread(_execute, sql)


if __name__ == "__main__":
    mcp.run()
