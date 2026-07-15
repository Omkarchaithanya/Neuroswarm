"""Serialization round-trip tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.rollback import (
    RollbackSerializer,
    SerializationError,
    dumps,
    loads,
)

from .conftest import fresh_manager, make_failure, make_operation


def test_json_roundtrip_operation():
    op = make_operation(rollback_id="rb_serde")
    raw = dumps(op, fmt="json")
    loaded = loads(raw, fmt="json")
    assert loaded.rollback_id == op.rollback_id
    assert loaded.checksum == op.checksum


def test_json_roundtrip_plan():
    mgr = fresh_manager()
    plan = mgr.plan(make_failure())
    ser = RollbackSerializer()
    raw = ser.dumps(plan, fmt="json")
    loaded = ser.loads(raw, fmt="json")
    assert loaded.plan_id == plan.plan_id
    assert loaded.strategy == plan.strategy


def test_dict_roundtrip():
    op = make_operation()
    ser = RollbackSerializer()
    payload = ser.dumps_dict(op)
    assert payload["schema_version"] == 1
    assert payload["kind"] == "rollback_operation"
    loaded = ser.loads_dict(payload)
    assert loaded.workflow_id == op.workflow_id


def test_unsupported_format():
    with pytest.raises(SerializationError):
        dumps(make_operation(), fmt="xml")


def test_yaml_roundtrip():
    pytest.importorskip("yaml")
    op = make_operation(rollback_id="rb_yaml")
    raw = dumps(op, fmt="yaml")
    loaded = loads(raw, fmt="yaml")
    assert loaded.rollback_id == "rb_yaml"
