"""Lifecycle tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    LifecycleError,
    LifecycleState,
    can_transition,
    is_selectable,
    transition,
)


def test_transitions():
    assert can_transition(LifecycleState.CREATED, LifecycleState.REGISTERED)
    assert can_transition(LifecycleState.REGISTERED, LifecycleState.READY)
    assert can_transition(LifecycleState.READY, LifecycleState.DEPRECATED)
    assert can_transition(LifecycleState.READY, LifecycleState.ARCHIVED)
    assert not can_transition(LifecycleState.ARCHIVED, LifecycleState.READY)
    assert not can_transition(LifecycleState.CREATED, LifecycleState.READY)


def test_transition_helper():
    assert (
        transition("t", LifecycleState.CREATED, LifecycleState.REGISTERED)
        is LifecycleState.REGISTERED
    )
    with pytest.raises(LifecycleError):
        transition("t", LifecycleState.CREATED, LifecycleState.READY)


def test_is_selectable():
    assert is_selectable(LifecycleState.READY)
    assert not is_selectable(LifecycleState.REGISTERED)
    assert not is_selectable(LifecycleState.DEPRECATED)


def test_registry_lifecycle(empty_registry, sample_template):
    rec = empty_registry.register(sample_template)
    assert rec.status is LifecycleState.REGISTERED
    ready = empty_registry.set_status(rec.id, LifecycleState.READY)
    assert ready.status is LifecycleState.READY
    deprecated = empty_registry.set_status(rec.id, LifecycleState.DEPRECATED)
    assert deprecated.status is LifecycleState.DEPRECATED
    archived = empty_registry.set_status(rec.id, LifecycleState.ARCHIVED)
    assert archived.status is LifecycleState.ARCHIVED
    with pytest.raises(LifecycleError):
        empty_registry.set_status(rec.id, LifecycleState.READY)
