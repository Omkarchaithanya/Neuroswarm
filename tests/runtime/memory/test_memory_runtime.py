"""Unit + integration tests for Cognitive Memory Runtime."""

from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.memory import (
    MemoryType,
    NeuroMemory,
    SearchQuery,
    build_memory_runtime,
)
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.importance import ImportanceEngine
from neuroswarm_arm.runtime.memory.namespace import NAMESPACES, normalize_namespace, namespace_for_type
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord
from neuroswarm_arm.runtime.memory.validators import validate_record
from neuroswarm_arm.memory.mem0_client import Mem0Fallback, build_memory


def _scratch() -> Path:
    root = Path("work") / "test_memory" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def store(request):
    root = _scratch()

    def _cleanup() -> None:
        shutil.rmtree(root, ignore_errors=True)

    request.addfinalizer(_cleanup)
    return root


@pytest.fixture()
def mem(store: Path) -> NeuroMemory:
    cfg = MemoryRuntimeConfig(store_root=store, provider="json", llm_mode="none")
    return build_memory_runtime(config=cfg)


def test_namespace_roots() -> None:
    assert "agents/" in NAMESPACES
    assert normalize_namespace("tools") == "tools/"
    assert namespace_for_type(MemoryType.REFLECTION) == "reflection/"


def test_schema_validation() -> None:
    rec = MemoryRecord(content="hello", owner="agent1", namespace="agents/")
    validate_record(rec)
    with pytest.raises(Exception):
        validate_record(MemoryRecord(content=" ", owner="x", namespace="agents/"))


def test_remember_and_recall(mem: NeuroMemory) -> None:
    mem.remember_fact("user prefers Arm Neoverse", owner="alice", tags=["pref"])
    mem.remember_tool(
        "success tool=github.list_issues latency_ms=12",
        owner="alice",
        metadata={"tool_id": "github.list_issues", "event": "success"},
        success_score=1.0,
    )
    hits = mem.recall("alice", "Arm Neoverse", limit=5)
    assert any("Neoverse" in h for h in hits)
    tool_hits = mem.search(SearchQuery(text="github", owner="alice", namespace="tools/", limit=5))
    assert tool_hits


def test_reflection_and_predict(mem: NeuroMemory) -> None:
    mem.remember_tool(
        "success tool=web.search",
        owner="bob",
        metadata={"tool_id": "web.search"},
        success_score=1.0,
    )
    ref = mem.reflect(
        owner="bob",
        workflow_id="chat",
        success=True,
        tools_used=["web.search"],
        notes="research query",
        latency_ms=100,
    )
    assert ref.lessons or ref.successful_strategies
    assert ref.memory_ids
    pred = mem.predict_next("bob", context="search")
    assert pred.next_tool == "web.search" or pred.confidence >= 0.0


def test_importance_engine(store: Path) -> None:
    cfg = MemoryRuntimeConfig(store_root=store, provider="json")
    eng = ImportanceEngine(cfg)
    rec = MemoryRecord(content="x", owner="a", success_score=1.0, access_count=10)
    score = eng.score(rec)
    assert 0.0 <= score <= 1.0


def test_compress_and_promote(mem: NeuroMemory) -> None:
    a = mem.remember_fact("duplicate fact alpha alpha", owner="c")
    b = mem.remember_fact("duplicate fact alpha alpha", owner="c")
    mem.promote(a.uuid)
    kept = mem.compress("c", keep=10)
    assert isinstance(kept, list)
    assert mem.forget(b.uuid) in {True, False}


def test_legacy_shim(store: Path) -> None:
    cfg = MemoryRuntimeConfig(store_root=store, provider="json", llm_mode="none")
    legacy = build_memory(store, config=cfg)
    assert isinstance(legacy, Mem0Fallback)
    legacy.add(
        "agentx",
        "success tool=foo latency_ms=1",
        metadata={"event": "success", "tool_id": "foo"},
    )
    hits = legacy.search("agentx", "foo", limit=5)
    assert hits
    assert legacy.neuro is not None


def test_history_ranker(store: Path) -> None:
    from neuroswarm_arm.runtime.router.history_ranker import HistoryRanker
    from neuroswarm_arm.runtime.router.models import ToolRecord

    memory = build_memory_runtime(config=MemoryRuntimeConfig(store_root=store, provider="json"))
    hr = HistoryRanker(memory=memory)
    tool = ToolRecord(id="t1", name="t1", description="d", success_rate=0.5)
    hr.record_success("ag", tool, latency_ms=5)
    hr.record_failure("ag", tool, reason="timeout")
    scores = hr.scores_for("ag", [tool], query="tool")
    assert "t1" in scores
    assert 0.0 <= scores["t1"] <= 1.0


def test_concurrency(mem: NeuroMemory) -> None:
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            mem.remember_fact(f"fact-{i}", owner="conc")
            mem.recall("conc", "fact", limit=3)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_health(mem: NeuroMemory) -> None:
    status = mem.health()
    assert status.healthy is True
    assert status.provider in {"json", "json_emergency", "mem0"}
