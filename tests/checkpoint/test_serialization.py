"""Serialization round-trip tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.checkpoint import CheckpointSerializer, SCHEMA_VERSION

from .conftest import make_checkpoint


def test_json_roundtrip() -> None:
    ser = CheckpointSerializer()
    ckpt = make_checkpoint()
    raw = ser.dumps(ckpt, fmt="json")
    loaded = ser.loads(raw, fmt="json")
    assert loaded.checkpoint_id == ckpt.checkpoint_id
    assert loaded.checksum == ckpt.checksum
    assert loaded.verify_checksum()


def test_dict_roundtrip() -> None:
    ser = CheckpointSerializer()
    ckpt = make_checkpoint()
    payload = ser.dumps_dict(ckpt)
    assert payload["schema_version"] == SCHEMA_VERSION
    loaded = ser.loads_dict(payload)
    assert loaded.execution_id == ckpt.execution_id


def test_yaml_roundtrip_if_available() -> None:
    ser = CheckpointSerializer()
    ckpt = make_checkpoint()
    try:
        raw = ser.dumps(ckpt, fmt="yaml")
    except Exception:
        return
    loaded = ser.loads(raw, fmt="yaml")
    assert loaded.checkpoint_id == ckpt.checkpoint_id
