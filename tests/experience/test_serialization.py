from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.experience import (
    ExperienceSerializer,
    dumps,
    loads,
    migrate,
)
from neuroswarm_arm.runtime.swarm.experience.exceptions import VersionMismatchError

from .conftest import make_record


def test_json_roundtrip():
    rec = make_record(execution_id="ser_1")
    raw = dumps(rec, fmt="json")
    loaded = loads(raw, fmt="json")
    assert loaded.execution_id == rec.execution_id
    assert loaded.content_hash == rec.content_hash


def test_yaml_roundtrip():
    rec = make_record(execution_id="ser_yaml")
    ser = ExperienceSerializer()
    raw = ser.dumps_record(rec, fmt="yaml")
    loaded = ser.loads_record(raw, fmt="yaml")
    assert loaded.workflow_id == rec.workflow_id


def test_migrate_identity():
    payload = {"schema_version": 1, "kind": "execution_record", "data": {"x": 1}}
    assert migrate(payload)["schema_version"] == 1


def test_migrate_future_rejected():
    with pytest.raises(VersionMismatchError):
        migrate({"schema_version": 99, "data": {}})
