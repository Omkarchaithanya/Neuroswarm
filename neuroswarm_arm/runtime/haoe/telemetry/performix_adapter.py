"""Performix adapter — JSON utilization snapshots (no circular evolution import)."""

from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any, Mapping


class PerformixAdapter:
    def __init__(self, snapshot_path: Path | None = None) -> None:
        self.path = Path(snapshot_path) if snapshot_path else None

    def write_snapshot(self, payload: Mapping[str, Any]) -> Path | None:
        if self.path is None:
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"ts": time(), "source": "haoe", **dict(payload)}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)
        return self.path

    def read_snapshot(self) -> dict[str, Any] | None:
        if self.path is None or not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
