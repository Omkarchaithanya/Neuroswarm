"""Versioning / migration tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.rollback import (
    SCHEMA_VERSION,
    VersionMismatchError,
    current_version,
    migrate_payload,
    register_migration,
)
from neuroswarm_arm.runtime.swarm.rollback.serializer import RollbackSerializer

from .conftest import make_operation


def test_current_version():
    assert current_version() == SCHEMA_VERSION == 1


def test_migrate_identity():
    op = make_operation()
    payload = {
        "schema_version": 1,
        "kind": "rollback_operation",
        "data": op.model_dump(mode="json"),
    }
    migrated = migrate_payload(payload)
    assert migrated["schema_version"] == 1
    loaded = RollbackSerializer().loads_dict(migrated)
    assert loaded.rollback_id == op.rollback_id


def test_future_version_rejected():
    with pytest.raises(VersionMismatchError):
        migrate_payload({"schema_version": 99, "data": {}})


def test_register_migration_noop_path():
    # Register a no-op from v1→v2 but SCHEMA_VERSION stays 1 so unused
    register_migration(1, lambda d: {**d, "migrated": True})
    payload = migrate_payload({"schema_version": 1, "data": {"x": 1}})
    assert payload["schema_version"] == 1
