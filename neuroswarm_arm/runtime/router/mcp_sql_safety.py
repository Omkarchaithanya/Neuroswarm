"""Postgres SQL safety helpers (read-only gate)."""

from __future__ import annotations

import re

_READ_PREFIX = re.compile(
    r"^\s*(WITH|SELECT|EXPLAIN|SHOW|VALUES)\b",
    re.IGNORECASE | re.DOTALL,
)
_WRITE_OR_DANGER = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|COPY|CALL|DO|GRANT|REVOKE|EXECUTE)\b",
    re.IGNORECASE,
)
_SELECT_INTO = re.compile(
    r"\bSELECT\b[\s\S]*?\bINTO\b",
    re.IGNORECASE,
)
_FORBIDDEN_FUNCS = re.compile(
    r"\b(pg_read_file|pg_ls_dir|lo_import|lo_export|dblink|pg_execute_server_program)\s*\(",
    re.IGNORECASE,
)


class SqlSafetyError(ValueError):
    pass


def assert_single_readonly_statement(sql: str) -> str:
    """Allow a single read-only statement; reject stacked / mutating SQL."""
    if not sql or not str(sql).strip():
        raise SqlSafetyError("sql is required")
    text = str(sql).strip()
    # Strip trailing semicolon for single-statement check
    core = text.rstrip().rstrip(";").strip()
    if ";" in core:
        raise SqlSafetyError("stacked / multi-statement SQL is not allowed")
    if not _READ_PREFIX.match(core):
        raise SqlSafetyError(
            "only SELECT/WITH/EXPLAIN/SHOW/VALUES statements are allowed on the read-only path"
        )
    if _SELECT_INTO.search(core):
        raise SqlSafetyError("SELECT INTO is not allowed on the read-only path")
    # EXPLAIN <mutating> still dangerous — check remainder after EXPLAIN [ANALYZE]
    body = core
    m = re.match(r"^\s*EXPLAIN(?:\s+ANALYZE)?\s+", core, re.IGNORECASE)
    if m:
        body = core[m.end() :]
        if body and _WRITE_OR_DANGER.search(body):
            raise SqlSafetyError("EXPLAIN of mutating statements is not allowed")
        if body and _SELECT_INTO.search(body):
            raise SqlSafetyError("EXPLAIN of SELECT INTO is not allowed")
    elif _WRITE_OR_DANGER.search(core):
        # Already required SELECT/WITH prefix; still block COPY/CALL embedded
        if re.search(
            r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|COPY|CALL|DO)\b",
            core,
            re.IGNORECASE,
        ):
            raise SqlSafetyError("mutating keywords are not allowed in read-only SQL")
    if _FORBIDDEN_FUNCS.search(core):
        raise SqlSafetyError("forbidden database function in SQL")
    return core
