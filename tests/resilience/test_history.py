"""Recovery history tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import (
    DecisionKind,
    RecoveryHistory,
    RecoveryRecord,
)


def test_append_and_list():
    hist = RecoveryHistory()
    hist.append(
        RecoveryRecord(
            record_id="r1",
            execution_id="ex1",
            previous_model="A",
            new_model="B",
            recovery_success=True,
            quality_delta=-0.1,
        )
    )
    hist.append(
        RecoveryRecord(
            record_id="r2",
            execution_id="ex2",
            previous_model="B",
            new_model="C",
            recovery_success=False,
            quality_delta=-0.2,
        )
    )
    assert len(hist) == 2
    assert hist.latest("ex1").new_model == "B"
    assert hist.success_rate() == 0.5
    assert hist.average_degradation() == (-0.1 + -0.2) / 2


def test_filter_by_execution():
    hist = RecoveryHistory()
    hist.append(
        RecoveryRecord(
            record_id="r1",
            execution_id="ex1",
            recovery_success=True,
            decision=DecisionKind.TRANSITION,
        )
    )
    hist.append(
        RecoveryRecord(
            record_id="r2",
            execution_id="ex2",
            recovery_success=True,
        )
    )
    assert len(hist.list(execution_id="ex1")) == 1


def test_to_dicts():
    hist = RecoveryHistory()
    hist.append(RecoveryRecord(record_id="r1", previous_model="A", new_model="B"))
    assert hist.to_dicts()[0]["record_id"] == "r1"
