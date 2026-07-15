"""Stress / load smoke tests for Cognitive Memory Runtime."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.memory import build_memory_runtime
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig


@pytest.mark.stress
def test_load_remember_search() -> None:
    root = Path("work") / "test_memory" / f"stress-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        mem = build_memory_runtime(config=MemoryRuntimeConfig(store_root=root, provider="json"))
        for i in range(200):
            mem.remember_fact(f"load fact number {i} about routing", owner="load")
        hits = mem.recall("load", "routing", limit=10)
        assert len(hits) >= 1
    finally:
        shutil.rmtree(root, ignore_errors=True)
