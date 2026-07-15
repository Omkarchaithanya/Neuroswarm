"""Schema version helpers and migration registry for Rollback Manager."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .exceptions import VersionMismatchError

SCHEMA_VERSION = 1

Migrator = Callable[[dict[str, Any]], dict[str, Any]]

_MIGRATIONS: dict[int, Migrator] = {}


def register_migration(from_version: int, migrator: Migrator) -> None:
    """Register a one-step migrator from ``from_version`` → ``from_version + 1``."""
    _MIGRATIONS[from_version] = migrator


def current_version() -> int:
    return SCHEMA_VERSION


def migrate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate a serialized rollback payload to SCHEMA_VERSION."""
    data = dict(payload)
    version = int(data.get("schema_version", data.get("version", SCHEMA_VERSION)))
    if version > SCHEMA_VERSION:
        raise VersionMismatchError(version, SCHEMA_VERSION)
    if version < 1:
        raise VersionMismatchError(version, SCHEMA_VERSION)
    while version < SCHEMA_VERSION:
        migrator = _MIGRATIONS.get(version)
        if migrator is None:
            break
        data = migrator(data)
        version += 1
        data["schema_version"] = version
    data["schema_version"] = SCHEMA_VERSION
    return data
