"""Retention tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from neuroswarm_arm.runtime.swarm.checkpoint import (
    CheckpointStatus,
    RetentionError,
    RetentionPolicy,
)

from .conftest import fresh_manager, make_checkpoint


def test_max_active_per_execution_archives_oldest() -> None:
    mgr = fresh_manager()
    for _ in range(5):
        mgr.checkpoint(make_checkpoint())

    result = mgr.apply_retention(RetentionPolicy(max_active_per_execution=2))
    assert len(result["archived"]) >= 3
    active = mgr.list_execution("ex_test", include_archived=False)
    assert len(active) == 2


def test_hard_delete_rejected() -> None:
    mgr = fresh_manager()
    with pytest.raises(RetentionError):
        mgr.apply_retention(RetentionPolicy(allow_hard_delete=True))


def test_archive_status_on_envelope() -> None:
    mgr = fresh_manager()
    stored = mgr.checkpoint(make_checkpoint())
    mgr.apply_retention(RetentionPolicy(max_active_total=0))
    env = mgr.repository.get_envelope(stored.checkpoint_id)
    assert env.status == CheckpointStatus.ARCHIVED
