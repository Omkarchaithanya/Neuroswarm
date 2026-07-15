"""Rollback Manager serializer — JSON / YAML + schema migration."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .exceptions import SerializationError
from .recovery import RollbackPlan
from .rollback import RollbackOperation
from .versioning import SCHEMA_VERSION, migrate_payload


class RollbackSerializer:
    """Serialize / deserialize RollbackOperation and RollbackPlan."""

    def dumps(self, obj: RollbackOperation | RollbackPlan, *, fmt: str = "json") -> str:
        kind = (
            "rollback_operation"
            if isinstance(obj, RollbackOperation)
            else "rollback_plan"
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "data": obj.model_dump(mode="json"),
        }
        return self._encode(payload, fmt)

    def loads(self, raw: str, *, fmt: str = "json") -> RollbackOperation | RollbackPlan:
        payload = migrate_payload(self._decode(raw, fmt))
        return self._from_payload(payload)

    def dumps_dict(self, obj: RollbackOperation | RollbackPlan) -> dict[str, Any]:
        kind = (
            "rollback_operation"
            if isinstance(obj, RollbackOperation)
            else "rollback_plan"
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "data": obj.model_dump(mode="json"),
        }

    def loads_dict(
        self, payload: Mapping[str, Any]
    ) -> RollbackOperation | RollbackPlan:
        migrated = migrate_payload(payload)
        return self._from_payload(migrated)

    def _from_payload(
        self, payload: Mapping[str, Any]
    ) -> RollbackOperation | RollbackPlan:
        data = payload.get("data", payload)
        kind = payload.get("kind", "rollback_operation")
        if kind == "rollback_plan":
            return RollbackPlan.model_validate(data)
        return RollbackOperation.model_validate(data)

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


def dumps(obj: RollbackOperation | RollbackPlan, *, fmt: str = "json") -> str:
    return RollbackSerializer().dumps(obj, fmt=fmt)


def loads(raw: str, *, fmt: str = "json") -> RollbackOperation | RollbackPlan:
    return RollbackSerializer().loads(raw, fmt=fmt)
