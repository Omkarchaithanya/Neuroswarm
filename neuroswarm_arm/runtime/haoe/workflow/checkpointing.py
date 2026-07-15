"""Workflow checkpointing — software filesystem store (Axion path)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        workflow_id: str,
        node_id: str,
        payload: dict[str, Any],
    ) -> Path:
        wf_dir = self.root / workflow_id
        wf_dir.mkdir(parents=True, exist_ok=True)
        path = wf_dir / f"{node_id}.json"
        tmp = wf_dir / f".{node_id}.{uuid4().hex}.tmp"
        data = {
            "workflow_id": workflow_id,
            "node_id": node_id,
            "payload": payload,
        }
        tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, workflow_id: str, node_id: str) -> dict[str, Any] | None:
        path = self.root / workflow_id / f"{node_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_nodes(self, workflow_id: str) -> list[str]:
        wf_dir = self.root / workflow_id
        if not wf_dir.exists():
            return []
        return [p.stem for p in wf_dir.glob("*.json")]
