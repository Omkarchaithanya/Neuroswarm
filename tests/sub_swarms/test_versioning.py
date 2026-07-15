"""Versioning tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    VersionError,
    bump_semver,
    compare_semver,
    parse_semver,
    versions_compatible,
)


def test_parse_and_compare():
    assert parse_semver("1.2.3")[:3] == (1, 2, 3)
    assert compare_semver("1.0.0", "1.0.1") == -1
    assert compare_semver("2.0.0", "1.9.9") == 1
    assert compare_semver("1.0.0", "1.0.0") == 0


def test_bump():
    assert bump_semver("1.0.0", part="patch") == "1.0.1"
    assert bump_semver("1.0.0", part="minor") == "1.1.0"
    assert bump_semver("1.0.0", part="major") == "2.0.0"


def test_invalid_semver():
    with pytest.raises(VersionError):
        parse_semver("not-a-version")


def test_compatible():
    assert versions_compatible("1.0.0", "1.2.0")
    assert not versions_compatible("1.0.0", "2.0.0")
    assert not versions_compatible("1.2.0", "1.1.0")
