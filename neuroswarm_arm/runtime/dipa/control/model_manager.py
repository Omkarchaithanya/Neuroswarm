"""ModelManager — opaque model registry (no backend paths leaked upward)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class ModelRecord:
    handle: str
    model_ref: str
    backend: str = ""
    quant: str = ""
    loaded_at: float = 0.0
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelManager:
    """Track loaded model handles. Backend attach is delegated to BackendManager."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._models: dict[str, ModelRecord] = {}
        self._by_ref: dict[str, str] = {}

    def load(
        self,
        model_ref: str,
        *,
        backend: str = "",
        quant: str = "",
        options: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        with self._lock:
            existing = self._by_ref.get(model_ref)
            if existing and existing in self._models:
                return existing
            handle = f"mdl_{uuid.uuid4().hex[:12]}"
            rec = ModelRecord(
                handle=handle,
                model_ref=model_ref,
                backend=backend,
                quant=quant,
                loaded_at=time.time(),
                options=dict(options or {}),
                metadata=dict(metadata or {}),
            )
            self._models[handle] = rec
            self._by_ref[model_ref] = handle
            return handle

    def get(self, handle: str) -> ModelRecord | None:
        with self._lock:
            return self._models.get(handle)

    def resolve(self, model_ref: str) -> ModelRecord | None:
        with self._lock:
            h = self._by_ref.get(model_ref)
            return self._models.get(h) if h else None

    def unload(self, handle: str) -> bool:
        with self._lock:
            rec = self._models.pop(handle, None)
            if rec is None:
                return False
            self._by_ref.pop(rec.model_ref, None)
            return True

    def list(self) -> list[ModelRecord]:
        with self._lock:
            return list(self._models.values())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._models),
                "models": [
                    {
                        "handle": m.handle,
                        "model_ref": m.model_ref,
                        "backend": m.backend,
                        "quant": m.quant,
                    }
                    for m in self._models.values()
                ],
            }
