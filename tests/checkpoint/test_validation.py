"""Validation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.checkpoint import (
    ChecksumMismatchError,
    CheckpointPolicy,
    CheckpointValidator,
    ValidationError,
)

from .conftest import make_checkpoint


def test_valid_checkpoint_passes() -> None:
    v = CheckpointValidator()
    ckpt = make_checkpoint()
    assert v.validate_checkpoint(ckpt) is ckpt


def test_checksum_mismatch() -> None:
    v = CheckpointValidator()
    ckpt = make_checkpoint()
    # Break checksum via object.__setattr__ on frozen model
    object.__setattr__(ckpt, "checksum", "deadbeef")
    with pytest.raises(ChecksumMismatchError):
        v.validate_checkpoint(ckpt)


def test_create_metadata_requires_ids() -> None:
    v = CheckpointValidator()
    with pytest.raises(ValidationError):
        v.validate_create_metadata({"workflow_id": "wf"})
    with pytest.raises(ValidationError):
        v.validate_create_metadata({"execution_id": "ex"})


def test_policy_validation() -> None:
    v = CheckpointValidator()
    with pytest.raises(Exception):
        CheckpointPolicy.every_n_nodes(0)
    ok = CheckpointPolicy.every_n_nodes(3)
    assert v.validate_policy(ok) is ok
