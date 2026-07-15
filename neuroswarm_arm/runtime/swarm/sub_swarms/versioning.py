"""Semver helpers + schema migration for Sub Swarms."""

from __future__ import annotations

import re
from typing import Any

from .exceptions import VersionError

SCHEMA_VERSION = 1

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def parse_semver(version: str) -> tuple[int, int, int, str, str]:
    match = _SEMVER_RE.match(version.strip())
    if not match:
        raise VersionError(f"invalid semver: {version!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        match.group("prerelease") or "",
        match.group("build") or "",
    )


def compare_semver(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if equal, 1 if a > b (prerelease ignored for ordering)."""
    am, an, ap, _, _ = parse_semver(a)
    bm, bn, bp, _, _ = parse_semver(b)
    if (am, an, ap) < (bm, bn, bp):
        return -1
    if (am, an, ap) > (bm, bn, bp):
        return 1
    return 0


def bump_semver(version: str, *, part: str = "patch") -> str:
    major, minor, patch, pre, build = parse_semver(version)
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    elif part == "patch":
        patch += 1
    else:
        raise VersionError(f"unknown bump part: {part}")
    base = f"{major}.{minor}.{patch}"
    if pre:
        base = f"{base}-{pre}"
    if build:
        base = f"{base}+{build}"
    return base


def migrate(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade serialized payloads to current SCHEMA_VERSION."""
    version = int(payload.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise VersionError(
            f"unsupported schema_version {version} (max {SCHEMA_VERSION})"
        )
    if version < 1:
        payload["schema_version"] = 1
    # v1 is current — placeholder for future migrations
    payload["schema_version"] = SCHEMA_VERSION
    return payload


def versions_compatible(required: str, available: str) -> bool:
    """Major must match; available minor/patch must be >= required."""
    rm, rn, rp, _, _ = parse_semver(required)
    am, an, ap, _, _ = parse_semver(available)
    if rm != am:
        return False
    return (an, ap) >= (rn, rp)
