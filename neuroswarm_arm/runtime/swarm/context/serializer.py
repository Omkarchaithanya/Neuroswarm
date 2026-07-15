"""Serialization for SwarmContext (JSON / YAML / Pydantic)."""

from __future__ import annotations

import json
from typing import Any

from .context import SwarmContext
from .exceptions import SerializationError
from .models import SerializationFormat
from .versioning import CONTEXT_SCHEMA_VERSION, migrate


def _ensure_version(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    data.setdefault("version", CONTEXT_SCHEMA_VERSION)
    data.setdefault("schema_version", data["version"])
    return data


def to_dict(ctx: SwarmContext) -> dict[str, Any]:
    return _ensure_version(ctx.model_dump(mode="json"))


def from_dict(data: dict[str, Any], *, migrate_schema: bool = True) -> SwarmContext:
    try:
        payload = dict(data)
        if migrate_schema:
            payload = migrate(payload)
        else:
            payload = _ensure_version(payload)
        return SwarmContext.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — wrap for API boundary
        raise SerializationError(f"deserialize failed: {exc}") from exc


def dumps(
    ctx: SwarmContext,
    *,
    fmt: SerializationFormat | str = SerializationFormat.JSON,
    indent: int | None = 2,
) -> bytes:
    data = to_dict(ctx)
    fmt_v = SerializationFormat(fmt) if not isinstance(fmt, SerializationFormat) else fmt
    try:
        if fmt_v is SerializationFormat.JSON:
            text = json.dumps(data, indent=indent, default=str, sort_keys=True)
            return text.encode("utf-8")
        if fmt_v is SerializationFormat.YAML:
            import yaml

            text = yaml.safe_dump(data, sort_keys=True, default_flow_style=False)
            return text.encode("utf-8")
        raise SerializationError(f"unsupported format: {fmt_v}")
    except SerializationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SerializationError(f"serialize failed: {exc}") from exc


def loads(
    data: bytes | str,
    *,
    fmt: SerializationFormat | str = SerializationFormat.JSON,
    migrate_schema: bool = True,
) -> SwarmContext:
    raw = data.decode("utf-8") if isinstance(data, bytes) else data
    fmt_v = SerializationFormat(fmt) if not isinstance(fmt, SerializationFormat) else fmt
    try:
        if fmt_v is SerializationFormat.JSON:
            payload = json.loads(raw)
        elif fmt_v is SerializationFormat.YAML:
            import yaml

            payload = yaml.safe_load(raw)
        else:
            raise SerializationError(f"unsupported format: {fmt_v}")
        if not isinstance(payload, dict):
            raise SerializationError("payload must be a mapping")
        return from_dict(payload, migrate_schema=migrate_schema)
    except SerializationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SerializationError(f"deserialize failed: {exc}") from exc


class ContextSerializer:
    """Stateful serializer facade."""

    def __init__(self, *, default_fmt: SerializationFormat = SerializationFormat.JSON) -> None:
        self.default_fmt = default_fmt

    def dumps(self, ctx: SwarmContext, *, fmt: SerializationFormat | None = None) -> bytes:
        return dumps(ctx, fmt=fmt or self.default_fmt)

    def loads(self, data: bytes | str, *, fmt: SerializationFormat | None = None) -> SwarmContext:
        return loads(data, fmt=fmt or self.default_fmt)
