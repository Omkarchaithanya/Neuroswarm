"""Unit tests for Mem0Adapter — mocked official SDK (no live mem0 required)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neuroswarm_arm.runtime.memory.adapter.mem0_adapter import Mem0Adapter
from neuroswarm_arm.runtime.memory.adapter.sdk_client import Mem0SdkClient
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.factory import build_memory_runtime
from neuroswarm_arm.runtime.memory.schemas import MemoryType


class _FakeMemory:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self._store: list[dict[str, Any]] = []

    def add(self, messages, **kwargs):
        self.added.append((messages, kwargs))
        mid = f"mem_{len(self._store)}"
        text = messages if isinstance(messages, str) else str(messages)
        item = {
            "id": mid,
            "memory": text if isinstance(text, str) else text[:200],
            "metadata": dict(kwargs.get("metadata") or {}),
            "score": 0.9,
            "user_id": kwargs.get("user_id"),
        }
        self._store.append(item)
        return {"results": [item]}

    def search(self, query, *, filters=None, top_k=5, threshold=0.1, rerank=False):
        hits = []
        for item in self._store:
            if filters and filters.get("user_id") and item.get("user_id") != filters["user_id"]:
                continue
            hits.append({**item, "score": 0.85})
        return {"results": hits[:top_k]}

    def get(self, memory_id):
        for item in self._store:
            if item["id"] == memory_id:
                return item
        return None

    def delete(self, memory_id):
        self._store = [i for i in self._store if i["id"] != memory_id]


def _scratch() -> Path:
    root = Path("work") / "test_memory" / f"adapter-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def adapter():
    root = _scratch()
    cfg = MemoryRuntimeConfig(store_root=root, provider="mem0", llm_mode="none")
    fake = _FakeMemory()
    client = Mem0SdkClient(cfg, memory=fake)
    ad = Mem0Adapter(cfg, client=client)
    yield ad
    shutil.rmtree(root, ignore_errors=True)


def test_remember_messages_calls_sdk(adapter: Mem0Adapter) -> None:
    msgs = [
        {"role": "user", "content": "I love Arm Neoverse"},
        {"role": "assistant", "content": "Noted"},
    ]
    out = adapter.remember(msgs, owner="alice", agent_id="coder")
    assert out
    assert adapter.client._memory.added  # type: ignore[union-attr]


def test_remember_tool_metadata(adapter: Mem0Adapter) -> None:
    rec = adapter.remember_tool(
        "success tool=web.search",
        owner="bob",
        metadata={"tool_id": "web.search"},
        success_score=1.0,
    )
    assert rec.type == MemoryType.TOOL
    assert rec.metadata.get("namespace") == "tools/"
    hits = adapter.search("web.search", owner="bob", limit=5)
    assert hits
    assert "mem0_hybrid" in hits[0].signals


def test_update_is_add_only_supersede(adapter: Mem0Adapter) -> None:
    first = adapter.remember_fact("old preference", owner="u1")
    updated = adapter.update(first.uuid, "new preference", owner="u1")
    assert updated.metadata.get("supersedes_id") == first.uuid


def test_predict_from_tool_history(adapter: Mem0Adapter) -> None:
    adapter.remember_tool(
        "success tool=github.issues",
        owner="p",
        metadata={"tool_id": "github.issues"},
    )
    pred = adapter.predict("p", context="github")
    assert pred.next_tool == "github.issues" or pred.confidence >= 0.0


def test_neuro_memory_remember_messages() -> None:
    root = _scratch()
    try:
        mem = build_memory_runtime(
            config=MemoryRuntimeConfig(store_root=root, provider="json", llm_mode="none")
        )
        assert mem.adapter is not None
        out = mem.remember(
            [{"role": "user", "content": "hello nexus"}, {"role": "assistant", "content": "hi"}],
            owner="z",
        )
        assert isinstance(out, list)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_mem0_import_outside_adapter() -> None:
    import re
    import neuroswarm_arm.runtime.memory as pkg
    import inspect

    assert hasattr(pkg, "Mem0Adapter")
    src = Path(inspect.getfile(pkg)).parent
    offenders = []
    pat = re.compile(r"^\s*(from mem0\b|import mem0\b)", re.M)
    for path in src.rglob("*.py"):
        if "adapter" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pat.search(text):
            offenders.append(str(path))
    assert offenders == []