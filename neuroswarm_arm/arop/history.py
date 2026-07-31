"""Append-only AROP cycle audit log (history.jsonl)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_PATH = Path("work/arop/history.jsonl")


def append_history(
    record: dict[str, Any],
    path: Path | None = None,
) -> Path:
    """Append one JSON object as a line. Creates parent dirs as needed."""
    p = path or DEFAULT_HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    body = dict(record)
    if "timestamp" not in body:
        body["timestamp"] = datetime.now(timezone.utc).isoformat()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(body, sort_keys=False) + "\n")
    return p


def read_history(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DEFAULT_HISTORY_PATH
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows
