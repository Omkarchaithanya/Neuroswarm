from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from neuroswarm_arm.runtime.swarm.experience import RecordLifecycle, RetentionPolicy
from neuroswarm_arm.runtime.swarm.experience.exceptions import RetentionError

from .conftest import fresh_store, make_record


def test_archive_and_age_retention():
    store = fresh_store()
    old = store.record(
        make_record(
            execution_id="old1",
            timestamp=datetime.now(timezone.utc) - timedelta(days=10),
        )
    )
    store.record(make_record(execution_id="new1"))
    result = store.apply_retention(RetentionPolicy(max_age=timedelta(days=5)))
    assert old.execution_id in result["archived"]
    assert store.repository.get_envelope(old.execution_id).lifecycle == RecordLifecycle.ARCHIVED
    # still readable from archive
    assert store.get(old.execution_id).execution_id == old.execution_id
    # not in active index / filter
    assert old.execution_id not in store.query.index.by_execution
    assert all(r.execution_id != old.execution_id for r in store.filter())


def test_count_retention():
    store = fresh_store()
    for i in range(5):
        store.record(
            make_record(
                execution_id=f"c{i}",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=5 - i),
            )
        )
    result = store.apply_retention(RetentionPolicy(max_active_records=2))
    assert result["archived_count"] == 3
    assert len(store.filter()) == 2


def test_hard_delete_rejected():
    store = fresh_store()
    with pytest.raises(RetentionError):
        store.apply_retention(RetentionPolicy(allow_hard_delete=True))
