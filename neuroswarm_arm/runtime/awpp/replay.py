"""Append-only JSONL replay log for offline AWPP policy training."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .observation import Observation


class ReplayWriter:
    """Writes observation (+ optional prediction metadata) under work/awpp/replay/."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        self._path = self.root / f"observations-{day}.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        observation: Observation | Mapping[str, Any],
        *,
        prediction: Mapping[str, Any] | None = None,
    ) -> None:
        if isinstance(observation, Observation):
            payload: dict[str, Any] = observation.to_dict()
        else:
            payload = dict(observation)
        if prediction is not None:
            payload["prediction"] = dict(prediction)
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
