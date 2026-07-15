"""Checkpoint Manager serializer — JSON / YAML + schema migration."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .checkpoint import Checkpoint
from .exceptions import SerializationError
from .versioning import SCHEMA_VERSION, migrate_payload


class CheckpointSerializer:
    """Serialize / deserialize Checkpoint domain objects."""

    def dumps(self, checkpoint: Checkpoint, *, fmt: str = "json") -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "checkpoint",
            "data": checkpoint.model_dump(mode="json"),
        }
        return self._encode(payload, fmt)

    def loads(self, raw: str, *, fmt: str = "json") -> Checkpoint:
        payload = migrate_payload(self._decode(raw, fmt))
        data = payload.get("data", payload)
        return Checkpoint.model_validate(data)

    def dumps_dict(self, checkpoint: Checkpoint) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "checkpoint",
            "data": checkpoint.model_dump(mode="json"),
        }

    def loads_dict(self, payload: Mapping[str, Any]) -> Checkpoint:
        migrated = migrate_payload(payload)
        data = migrated.get("data", migrated)
        return Checkpoint.model_validate(data)

    def _encode(self, payload: dict[str, Any], fmt: str) -> str:
        fmt = fmt.lower()
        if fmt == "json":
            return json.dumps(payload, sort_keys=True, default=str)
        if fmt == "yaml":
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise SerializationError("PyYAML required for yaml format") from exc
            return yaml.safe_dump(payload, sort_keys=True)
        raise SerializationError(f"unsupported format: {fmt}")

    def _decode(self, raw: str, fmt: str) -> dict[str, Any]:
        fmt = fmt.lower()
        try:
            if fmt == "json":
                data = json.loads(raw)
            elif fmt == "yaml":
                try:
                    import yaml  # type: ignore
                except ImportError as exc:  # pragma: no cover
                    raise SerializationError("PyYAML required for yaml format") from exc
                data = yaml.safe_load(raw)
            else:
                raise SerializationError(f"unsupported format: {fmt}")
        except SerializationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SerializationError(str(exc)) from exc
        if not isinstance(data, dict):
            raise SerializationError("decoded payload must be a mapping")
        return data
