"""Serialization tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    SCHEMA_VERSION,
    SwarmSerializer,
    dumps,
    loads,
    migrate,
)


def test_json_roundtrip(sample_template):
    raw = dumps(sample_template, fmt="json")
    restored = loads(raw, fmt="json")
    assert restored.id == sample_template.id
    assert restored.content_hash() == sample_template.content_hash()


def test_yaml_roundtrip(sample_template):
    ser = SwarmSerializer()
    raw = ser.dumps_template(sample_template, fmt="yaml")
    restored = ser.loads_template(raw, fmt="yaml")
    assert restored.name == sample_template.name
    assert restored.required_agents == sample_template.required_agents


def test_registry_snapshot(manager):
    ser = SwarmSerializer()
    raw = ser.dumps_registry(manager.list_templates(), fmt="json")
    templates = ser.loads_registry(raw, fmt="json")
    assert len(templates) == 7


def test_migrate_sets_schema():
    payload = migrate({"schema_version": 1, "id": "x"})
    assert payload["schema_version"] == SCHEMA_VERSION
