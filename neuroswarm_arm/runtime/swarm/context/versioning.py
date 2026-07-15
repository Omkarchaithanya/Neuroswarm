"""Schema versioning + migration hooks for Swarm Context serialization."""

from __future__ import annotations

from typing import Any, Callable

from .exceptions import VersionMismatchError

CONTEXT_SCHEMA_VERSION = "1.0.0"

Migrator = Callable[[dict[str, Any]], dict[str, Any]]

_MIGRATIONS: dict[tuple[str, str], Migrator] = {}


def register_migration(from_version: str, to_version: str, fn: Migrator) -> None:
    _MIGRATIONS[(from_version, to_version)] = fn


def _identity(data: dict[str, Any]) -> dict[str, Any]:
    return data


# Identity path for current version (future: 1.0.0 -> 1.1.0 etc.)
register_migration("1.0.0", "1.0.0", _identity)


def normalize_version(version: str | None) -> str:
    if not version:
        return CONTEXT_SCHEMA_VERSION
    return version.strip()


def migrate(
    data: dict[str, Any],
    *,
    from_version: str | None = None,
    to_version: str = CONTEXT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Migrate a serialized context dict between schema versions.

    Currently only 1.0.0 exists; unknown versions raise VersionMismatchError.
    """
    src = normalize_version(from_version or data.get("version") or data.get("schema_version"))
    dst = normalize_version(to_version)
    if src == dst:
        out = dict(data)
        out["version"] = dst
        out["schema_version"] = dst
        return out
    key = (src, dst)
    if key not in _MIGRATIONS:
        # Try single-hop registry; if missing, fail loudly
        raise VersionMismatchError(found=src, expected=dst)
    out = _MIGRATIONS[key](dict(data))
    out["version"] = dst
    out["schema_version"] = dst
    return out


def assert_compatible(version: str | None) -> str:
    v = normalize_version(version)
    if v != CONTEXT_SCHEMA_VERSION and (v, CONTEXT_SCHEMA_VERSION) not in _MIGRATIONS:
        raise VersionMismatchError(found=v, expected=CONTEXT_SCHEMA_VERSION)
    return v
