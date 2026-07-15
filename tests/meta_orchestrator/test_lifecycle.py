"""Workflow lifecycle tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.meta_orchestrator import (
    WorkflowLifecycle,
    WorkflowStatus,
)
from neuroswarm_arm.runtime.swarm.meta_orchestrator.exceptions import InvalidWorkflowStateError
from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import WorkflowExecution


def test_happy_path_transitions() -> None:
    lc = WorkflowLifecycle()
    ex = WorkflowExecution(context={"ok": True}, graph={"nodes": {"a": {}}})
    assert ex.status == WorkflowStatus.CREATED
    lc.mark_ready(ex)
    lc.mark_running(ex)
    lc.mark_waiting(ex)
    lc.mark_running(ex)
    lc.mark_completed(ex)
    assert lc.is_terminal(ex)


def test_invalid_transition() -> None:
    lc = WorkflowLifecycle()
    ex = WorkflowExecution(context={"ok": True}, graph={"nodes": {"a": {}}})
    with pytest.raises(InvalidWorkflowStateError):
        lc.mark_completed(ex)


def test_checkpoint_restore_path() -> None:
    lc = WorkflowLifecycle()
    ex = WorkflowExecution(context={"ok": True}, graph={"nodes": {"a": {}}})
    lc.mark_ready(ex)
    lc.mark_running(ex)
    lc.mark_checkpointed(ex)
    lc.mark_restored(ex)
    lc.mark_ready(ex)
    assert ex.status == WorkflowStatus.READY
