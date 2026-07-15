"""Built-in template tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    BUILTIN_TEMPLATE_FACTORIES,
    LifecycleState,
    SwarmValidator,
    all_builtin_templates,
    build_sub_swarm_manager,
)


EXPECTED_IDS = {
    "nexus.swarms.research",
    "nexus.swarms.coding",
    "nexus.swarms.documentation",
    "nexus.swarms.tool_execution",
    "nexus.swarms.analysis",
    "nexus.swarms.planning",
    "nexus.swarms.benchmark",
}


def test_all_builtins_present():
    assert set(BUILTIN_TEMPLATE_FACTORIES) == EXPECTED_IDS
    templates = all_builtin_templates()
    assert len(templates) == 7
    assert {t.id for t in templates} == EXPECTED_IDS


def test_builtins_validate():
    validator = SwarmValidator()
    for tpl in all_builtin_templates():
        report = validator.validate(tpl)
        assert report.ok, f"{tpl.id}: {[i.message for i in report.errors]}"
        assert tpl.task_graph_reference.snapshot is not None
        assert tpl.required_agents


def test_manager_registers_ready():
    mgr = build_sub_swarm_manager()
    assert len(mgr.list_templates()) == 7
    assert len(mgr.list_ready()) == 7
    for tpl in mgr.list_ready():
        assert tpl.status is LifecycleState.READY


def test_executable_from_builtin(manager):
    desc = manager.to_executable("nexus.swarms.analysis")
    assert desc.template_id == "nexus.swarms.analysis"
    assert desc.task_graph.snapshot is not None
    assert len(desc.agents) >= 3
