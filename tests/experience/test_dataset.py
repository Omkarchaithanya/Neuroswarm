from __future__ import annotations

from pathlib import Path

import pytest

from neuroswarm_arm.runtime.swarm.experience import DatasetKind

from .conftest import fresh_store, make_record


@pytest.fixture
def out_dir(request):
    root = Path(__file__).resolve().parent / "_tmp" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    yield root


def test_all_dataset_kinds(out_dir):
    store = fresh_store()
    store.record(make_record(execution_id="d1"))
    store.record(make_record(execution_id="d2", workflow_id="wf_other"))

    for kind in (
        DatasetKind.BENCHMARK,
        DatasetKind.POLICY,
        DatasetKind.OFFLINE_RL,
        DatasetKind.ANALYTICS,
    ):
        ds = store.generate_dataset(kind)
        assert len(ds) == 2
        assert ds.kind is kind
        assert ds.rows

    path = store.export_dataset("benchmark", fmt="json", path=out_dir / "bench.json")
    assert Path(path).exists()
    assert store.metrics.dataset_exports >= 1


def test_offline_rl_shape():
    store = fresh_store()
    store.record(make_record(execution_id="rl1"))
    store.record(make_record(execution_id="rl2"))
    ds = store.generate_offline_rl_dataset()
    row = ds.rows[0]
    assert "state" in row and "action" in row and "reward" in row
    assert "next_state" in row and "done" in row
    assert ds.metadata.get("training") is False
