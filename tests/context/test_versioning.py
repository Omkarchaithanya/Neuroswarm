"""Versioning helpers."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.context import CONTEXT_SCHEMA_VERSION, migrate


def test_migrate_sets_schema_version():
    out = migrate({"request": {"prompt": "v"}}, from_version="1.0.0")
    assert out["version"] == CONTEXT_SCHEMA_VERSION
    assert out["schema_version"] == CONTEXT_SCHEMA_VERSION
