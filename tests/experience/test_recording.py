from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.swarm.experience import (
    DuplicateIdError,
    ImmutabilityError,
    WorkflowRecord,
)

from .conftest import fresh_store, make_record


@pytest.fixture
def out_dir(request):
    root = Path(__file__).resolve().parent / "_tmp" / request.node.name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_record_and_get():
    store = fresh_store()
    rec = store.record(make_record())
    got = store.get(rec.execution_id)
    assert got.execution_id == rec.execution_id
    assert got.content_hash
    assert got.workflow_id == "wf_test"


def test_duplicate_id_rejected():
    store = fresh_store()
    rec = store.record(make_record(execution_id="exec_fixed"))
    with pytest.raises(DuplicateIdError):
        store.record(make_record(execution_id=rec.execution_id))


def test_immutability_update_delete():
    store = fresh_store()
    store.record(make_record(execution_id="exec_imm"))
    with pytest.raises(ImmutabilityError):
        store.repository.update_execution(make_record(execution_id="exec_imm"))
    with pytest.raises(ImmutabilityError):
        store.repository.delete_execution("exec_imm")


def test_workflow_record():
    store = fresh_store()
    e1 = store.record(make_record(execution_id="e1"))
    e2 = store.record(make_record(execution_id="e2", workflow_id="wf_test"))
    wf = store.record_workflow(
        WorkflowRecord(
            workflow_id="wf_roll",
            execution_ids=[e1.execution_id, e2.execution_id],
            total_latency=200.0,
            total_cost=0.1,
        )
    )
    assert store.repository.get_workflow(wf.workflow_id).execution_ids == [
        e1.execution_id,
        e2.execution_id,
    ]


def test_jsonl_persistence(out_dir):
    root = out_dir / "exp"
    store = fresh_store(root=root)
    rec = store.record(make_record(execution_id="persist_1"))
    store2 = fresh_store(root=root)
    assert store2.get(rec.execution_id).content_hash == rec.content_hash


def test_metrics_increment():
    store = fresh_store()
    store.record(make_record())
    assert store.metrics.records_stored == 1
