from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.experience import (
    ExecutionRecord,
    QualityScore,
    validate_execution_record,
    validate_metrics,
)
from neuroswarm_arm.runtime.swarm.experience.exceptions import ValidationError
from neuroswarm_arm.runtime.swarm.experience.validators import CURRENT_SCHEMA_VERSION

from .conftest import make_record


def test_invalid_quality_rejected():
    with pytest.raises(Exception):
        QualityScore(execution=1.5)


def test_invalid_metrics():
    with pytest.raises(ValidationError):
        validate_metrics({"": 1.0})


def test_missing_workflow():
    with pytest.raises(Exception):
        ExecutionRecord(workflow_id="")


def test_hash_mismatch():
    rec = make_record(execution_id="h1")
    bad = rec.model_copy(update={"content_hash": "deadbeef"})
    with pytest.raises(ValidationError):
        validate_execution_record(bad, expected_version=CURRENT_SCHEMA_VERSION)
