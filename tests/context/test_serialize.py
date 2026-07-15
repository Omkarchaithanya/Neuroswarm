"""Serialization + versioning tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.context import (
    CONTEXT_SCHEMA_VERSION,
    SerializationFormat,
    SwarmContextBuilder,
    VersionMismatchError,
    assert_compatible,
    dumps,
    loads,
    migrate,
)


def test_json_roundtrip():
    ctx = (
        SwarmContextBuilder()
        .request(prompt="ser")
        .budget(tokens_limit=50, tokens_used=10)
        .memory(session_id="s1")
        .build()
    )
    raw = dumps(ctx, fmt=SerializationFormat.JSON)
    back = loads(raw, fmt=SerializationFormat.JSON)
    assert back.request.prompt == "ser"
    assert back.budget.tokens_used == 10
    assert back.memory.session_id == "s1"
    assert back.version == CONTEXT_SCHEMA_VERSION


def test_yaml_roundtrip():
    ctx = SwarmContextBuilder().request(prompt="yaml").build()
    raw = dumps(ctx, fmt=SerializationFormat.YAML)
    back = loads(raw, fmt=SerializationFormat.YAML)
    assert back.request.prompt == "yaml"


def test_migrate_identity():
    data = {"version": "1.0.0", "request": {"prompt": "m"}}
    out = migrate(data)
    assert out["version"] == CONTEXT_SCHEMA_VERSION


def test_version_mismatch():
    with pytest.raises(VersionMismatchError):
        assert_compatible("9.9.9")
