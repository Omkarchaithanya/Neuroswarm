"""Compatibility wrapper around the Plane-2 KV Memory Runtime.

Deprecated: prefer ``neuroswarm_arm.runtime.kv.build_kv_runtime``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.kv.factory import build_kv_runtime
from neuroswarm_arm.runtime.kv.manager.runtime import KVRuntimeManager
from neuroswarm_arm.runtime.kv.utils.config import load_kv_config


@dataclass
class KVPage:
    page_id: str
    data: bytes
    compressed: bool = False


@dataclass
class KVCachePager:
    """Legacy pager API backed by KVRuntimeManager checkpoint/restore."""

    root: Path
    pages: dict[str, KVPage] = field(default_factory=dict)
    _runtime: KVRuntimeManager | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        cfg = load_kv_config(self.root)
        self._runtime = build_kv_runtime(cfg, enable_background=False)

    @property
    def runtime(self) -> KVRuntimeManager:
        assert self._runtime is not None
        return self._runtime

    def save(self, session_id: str, payload: dict) -> Path:
        import anyio
        import json

        raw = json.dumps(payload).encode("utf-8")
        self.runtime.create_session(session_id)
        anyio.run(self.runtime.allocate, session_id, raw)
        anyio.run(self.runtime.checkpoint, session_id)
        self.pages[session_id] = KVPage(page_id=session_id, data=raw, compressed=True)
        assert self.runtime.config.checkpoint_dir is not None
        return self.runtime.config.checkpoint_dir / session_id / "meta.json"

    def load(self, session_id: str) -> dict:
        import anyio
        import json

        session = anyio.run(self.runtime.restore, session_id)
        # Reconstruct original JSON from first physical payload when possible
        for block in session.blocks.values():
            if block.physical_id:
                data = anyio.run(self.runtime.block_manager.read_payload, block.physical_id)
                try:
                    return json.loads(data.decode("utf-8"))
                except Exception:
                    continue
        raise KeyError(session_id)

    def pressure(self) -> float:
        return self.runtime.pressure_snapshot().pressure
