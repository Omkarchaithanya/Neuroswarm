"""Serialization round-trip tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import dumps, loads, build_agent_registry
from neuroswarm_arm.runtime.swarm.agent_registry.profile import coding_agent
from neuroswarm_arm.runtime.swarm.agent_registry.serializer import AgentSerializer


def test_json_roundtrip():
    a = coding_agent()
    raw = dumps(a, fmt="json")
    b = loads(raw, fmt="json")
    assert b.id == a.id
    assert b.name == a.name
    assert b.content_hash() == a.content_hash()


def test_yaml_roundtrip():
    a = coding_agent()
    ser = AgentSerializer()
    raw = ser.dumps_agent(a, fmt="yaml")
    b = ser.loads_agent(raw, fmt="yaml")
    assert b.id == a.id
    assert b.capabilities.supported_tasks == a.capabilities.supported_tasks


def test_registry_snapshot():
    svc = build_agent_registry()
    ser = AgentSerializer()
    raw = ser.dumps_registry(svc.registry.as_list(), fmt="json")
    agents = ser.loads_registry(raw, fmt="json")
    assert len(agents) == svc.registry.size()
