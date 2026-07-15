from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import fresh_store


@pytest.fixture
def out_dir(request):
    root = Path(__file__).resolve().parent / "_tmp" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    yield root


def test_snapshot_port_roundtrip():
    store = fresh_store()
    handle = store.store_snapshot({"context_id": "ctx_1", "blob": {"k": "v"}})
    assert handle.startswith("exp://snapshot/")
    loaded = store.load_snapshot(handle)
    assert loaded["context_id"] == "ctx_1"
    assert store.metrics.snapshots_stored == 1


def test_jsonl_snapshot(out_dir):
    store = fresh_store(root=out_dir / "snap")
    handle = store.store_snapshot({"x": 1})
    store2 = fresh_store(root=out_dir / "snap")
    assert store2.load_snapshot(handle)["x"] == 1
