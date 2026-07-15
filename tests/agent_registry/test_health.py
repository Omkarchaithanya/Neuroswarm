"""Health / heartbeat tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import build_agent_registry
from neuroswarm_arm.runtime.swarm.agent_registry.health import HealthRecord


def test_health_record_success_failure():
    h = HealthRecord()
    h2 = h.record_success(latency_ms=100.0, cost_usd=0.01)
    assert h2.success_count == 1
    assert h2.average_latency_ms == 100.0
    h3 = h2.record_failure(message="boom")
    assert h3.failure_count == 1
    assert h3.consecutive_failures == 1
    assert h3.success_rate < 1.0


def test_heartbeat_tick():
    svc = build_agent_registry()
    agent = svc.registry.as_list()[0]
    before = agent.health.last_heartbeat
    updated = svc.heartbeat.tick(agent.id)
    assert updated.health.last_heartbeat is not None
    assert updated.health.last_heartbeat != before


def test_record_success_updates_agent():
    svc = build_agent_registry()
    agent = svc.registry.get_by_name("router_agent")
    updated = svc.heartbeat.record_success(agent.id, latency_ms=50.0, cost_usd=0.0001)
    assert updated.health.success_count >= 1
    assert updated.health.average_latency_ms > 0
