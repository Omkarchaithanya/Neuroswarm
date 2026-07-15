"""Versioning / migration tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.resilience import (
    SCHEMA_VERSION,
    VersionMismatchError,
    current_version,
    migrate_payload,
    register_migration,
)


def test_current_version():
    assert current_version() == SCHEMA_VERSION == 1


def test_migrate_identity_for_v1():
    payload = {"schema_version": 1, "data": {"x": 1}}
    out = migrate_payload(payload)
    assert out["schema_version"] == 1
    assert out["data"]["x"] == 1


def test_reject_future_version():
    with pytest.raises(VersionMismatchError):
        migrate_payload({"schema_version": 99})


def test_reject_version_below_one():
    with pytest.raises(VersionMismatchError):
        migrate_payload({"schema_version": 0})


def test_register_migration_callable():
    # Register a no-op path for future bumps without changing SCHEMA_VERSION
    called = {"n": 0}

    def _mig(data: dict) -> dict:
        called["n"] += 1
        return data

    register_migration(1000, _mig)  # unused until SCHEMA_VERSION > 1000
    assert migrate_payload({"schema_version": 1})["schema_version"] == 1
    assert called["n"] == 0
