from __future__ import annotations

import json
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.swarm.experience import ExportFormat
from neuroswarm_arm.runtime.swarm.experience.exceptions import ExportError

from .conftest import fresh_store, make_record


@pytest.fixture
def out_dir(request):
    root = Path(__file__).resolve().parent / "_tmp" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    yield root


def test_export_json_and_csv(out_dir):
    store = fresh_store()
    store.record(make_record(execution_id="ex1"))
    store.record(make_record(execution_id="ex2"))

    text = store.export(fmt=ExportFormat.JSON)
    assert isinstance(text, str)
    data = json.loads(text)
    assert len(data) == 2

    csv_path = store.export(fmt="csv", path=out_dir / "out.csv")
    content = Path(csv_path).read_text(encoding="utf-8")
    assert "execution_id" in content
    assert "ex1" in content


def test_export_otel():
    store = fresh_store()
    store.record(make_record(execution_id="otel1"))
    text = store.export(fmt=ExportFormat.OTEL)
    payload = json.loads(text)
    assert payload[0]["name"] == "nexus.swarm.experience.execution"
    assert "nexus.swarm.experience.execution_id" in payload[0]["attributes"]


def test_export_parquet(out_dir):
    store = fresh_store()
    store.record(make_record(execution_id="pq1"))
    try:
        path = store.export(fmt=ExportFormat.PARQUET, path=out_dir / "out.parquet")
    except ExportError as exc:
        if "pyarrow" in str(exc):
            pytest.skip("pyarrow not installed")
        raise
    assert Path(path).exists()


def test_import_json_roundtrip():
    store = fresh_store()
    rec = make_record(execution_id="imp1")
    raw = json.dumps(rec.model_dump(mode="json"), default=str)
    imported = store.importer.import_json(raw)
    assert imported[0].execution_id == "imp1"
