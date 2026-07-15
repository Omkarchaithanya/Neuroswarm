"""Fluent builder tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.sub_swarms import SwarmBuilder, SwarmValidator


def test_fluent_builder():
    swarm = (
        SwarmBuilder()
        .template(
            id="nexus.swarms.fluent",
            name="fluent",
            workflow_type="custom",
            category="custom",
        )
        .agents("nexus.agents.planning_agent", "nexus.agents.coding_agent")
        .context("request", "budget")
        .budget("envelope_id", "max_cost_usd")
        .tools("nexus.tools.github")
        .models("qwen2.5-8b")
        .backends("llama.cpp")
        .task_graph(graph_id="g_fluent", graph_name="fluent", snapshot={"ok": True})
        .estimates(cost=0.02, latency=2000.0, memory=2048, cpu=4.0, tokens=1000.0)
        .parallelism(2)
        .priority(80)
        .tags("fluent", "builder")
        .labels(team="platform")
        .build()
    )
    assert swarm.id == "nexus.swarms.fluent"
    assert swarm.parallelism == 2
    assert swarm.priority == 80
    assert "request" in swarm.required_context
    assert swarm.labels["team"] == "platform"
    report = SwarmValidator().validate(swarm)
    assert report.ok


def test_builder_from_base(sample_template):
    swarm = (
        SwarmBuilder()
        .template(base=sample_template, id="nexus.swarms.from_base", name="from_base")
        .agents("nexus.agents.memory_agent")
        .build()
    )
    assert swarm.id == "nexus.swarms.from_base"
    assert "nexus.agents.memory_agent" in swarm.required_agents
    assert sample_template.id in swarm.metadata.composition_of
