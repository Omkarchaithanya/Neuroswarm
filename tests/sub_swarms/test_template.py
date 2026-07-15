"""Template creation and mutation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    LifecycleState,
    SwarmTemplate,
    TaskGraphReference,
)


def test_template_creation(sample_template):
    assert sample_template.id == "nexus.swarms.test_sample"
    assert sample_template.display_name
    assert sample_template.task_graph_reference.is_present
    assert len(sample_template.required_agents) == 2
    assert sample_template.status is LifecycleState.CREATED


def test_content_hash_stable(sample_template):
    h1 = sample_template.content_hash()
    h2 = sample_template.content_hash()
    assert h1 == h2
    assert len(h1) == 64


def test_clone_and_evolve(sample_template):
    cloned = sample_template.clone(new_id="nexus.swarms.cloned", new_name="cloned")
    assert cloned.id == "nexus.swarms.cloned"
    assert cloned.status is LifecycleState.CREATED
    assert sample_template.id in cloned.metadata.provenance

    evolved = cloned.evolve(priority=90)
    assert evolved.priority == 90
    assert evolved.updated_at >= cloned.updated_at


def test_bump_version(sample_template):
    bumped = sample_template.bump_version(part="minor")
    assert bumped.version == "1.1.0"


def test_freeze_blocks_evolve(sample_template):
    frozen = sample_template.freeze()
    with pytest.raises(ValueError, match="frozen"):
        frozen.evolve(priority=1)


def test_to_dict_roundtrip_fields(sample_template):
    data = sample_template.to_dict()
    restored = SwarmTemplate.model_validate(data)
    assert restored.id == sample_template.id
    assert restored.required_agents == sample_template.required_agents


def test_empty_id_rejected():
    with pytest.raises(Exception):
        SwarmTemplate(
            id="",
            name="x",
            task_graph_reference=TaskGraphReference(graph_id="g"),
            required_agents=["a"],
        )
