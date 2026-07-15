"""Versioning / migration tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.checkpoint import (
    SCHEMA_VERSION,
    VersionMismatchError,
    current_version,
    migrate_payload,
)


def test_current_version() -> None:
    assert current_version() == SCHEMA_VERSION == 1


def test_migrate_identity() -> None:
    payload = {"schema_version": 1, "data": {"workflow_id": "wf"}}
    out = migrate_payload(payload)
    assert out["schema_version"] == SCHEMA_VERSION


def test_migrate_rejects_future() -> None:
    with pytest.raises(VersionMismatchError):
        migrate_payload({"schema_version": 99, "data": {}})


def test_migrate_rejects_pre_v1() -> None:
    with pytest.raises(VersionMismatchError):
        migrate_payload({"schema_version": 0, "data": {}})
