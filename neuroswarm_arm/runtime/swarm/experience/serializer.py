"""Experience Store serializer — JSON / YAML + schema migration."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .execution_plan import ExecutionPlan
from .execution_record import ExecutionRecord
from .exceptions import SerializationError, VersionMismatchError
from .workflow_record import WorkflowRecord

SCHEMA_VERSION = 1


def migrate(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate a serialized experience payload to SCHEMA_VERSION."""
    data = dict(payload)
    version = int(data.get("schema_version", data.get("version", SCHEMA_VERSION)))
    if version > SCHEMA_VERSION:
        raise VersionMismatchError(version, SCHEMA_VERSION)
    # v1 is current — identity migrator reserved for future bumps
    if version < 1:
        raise VersionMismatchError(version, SCHEMA_VERSION)
    data["schema_version"] = SCHEMA_VERSION
    return data


class ExperienceSerializer:
    """Serialize / deserialize experience domain objects."""

    def dumps_record(self, record: ExecutionRecord, *, fmt: str = "json") -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "execution_record",
            "data": record.model_dump(mode="json"),
        }
        return self._encode(payload, fmt)

    def loads_record(self, raw: str, *, fmt: str = "json") -> ExecutionRecord:
        payload = migrate(self._decode(raw, fmt))
        data = payload.get("data", payload)
        return ExecutionRecord.model_validate(data)

    def dumps_workflow(self, record: WorkflowRecord, *, fmt: str = "json") -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "workflow_record",
            "data": record.model_dump(mode="json"),
        }
        return self._encode(payload, fmt)

    def loads_workflow(self, raw: str, *, fmt: str = "json") -> WorkflowRecord:
        payload = migrate(self._decode(raw, fmt))
        data = payload.get("data", payload)
        return WorkflowRecord.model_validate(data)

    def dumps_plan(self, plan: ExecutionPlan, *, fmt: str = "json") -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "execution_plan",
            "data": plan.model_dump(mode="json"),
        }
        return self._encode(payload, fmt)

    def loads_plan(self, raw: str, *, fmt: str = "json") -> ExecutionPlan:
        payload = migrate(self._decode(raw, fmt))
        data = payload.get("data", payload)
        return ExecutionPlan.model_validate(data)

    def dumps(self, obj: Any, *, fmt: str = "json") -> str:
        if isinstance(obj, ExecutionRecord):
            return self.dumps_record(obj, fmt=fmt)
        if isinstance(obj, WorkflowRecord):
            return self.dumps_workflow(obj, fmt=fmt)
        if isinstance(obj, ExecutionPlan):
            return self.dumps_plan(obj, fmt=fmt)
        if hasattr(obj, "model_dump"):
            return self._encode(
                {"schema_version": SCHEMA_VERSION, "data": obj.model_dump(mode="json")},
                fmt,
            )
        raise SerializationError(f"unsupported type: {type(obj)!r}")

    def loads(self, raw: str, *, fmt: str = "json", kind: str | None = None) -> Any:
        payload = migrate(self._decode(raw, fmt))
        resolved = kind or payload.get("kind")
        data = payload.get("data", payload)
        if resolved == "execution_record" or (
            resolved is None and "execution_id" in data and "workflow_id" in data
        ):
            return ExecutionRecord.model_validate(data)
        if resolved == "workflow_record":
            return WorkflowRecord.model_validate(data)
        if resolved == "execution_plan":
            return ExecutionPlan.model_validate(data)
        raise SerializationError(f"cannot infer kind from payload: {resolved!r}")

    def _encode(self, payload: Mapping[str, Any], fmt: str) -> str:
        fmt = fmt.lower()
        try:
            if fmt == "json":
                return json.dumps(payload, indent=2, sort_keys=True, default=str)
            if fmt == "yaml":
                try:
                    import yaml
                except ImportError as exc:  # pragma: no cover
                    raise SerializationError("PyYAML required for yaml format") from exc
                return yaml.safe_dump(
                    dict(payload), sort_keys=True, default_flow_style=False
                )
            raise SerializationError(f"unsupported format: {fmt}")
        except SerializationError:
            raise
        except Exception as exc:  # pragma: no cover
            raise SerializationError(str(exc)) from exc

    def _decode(self, raw: str, fmt: str) -> dict[str, Any]:
        fmt = fmt.lower()
        try:
            if fmt == "json":
                data = json.loads(raw)
            elif fmt == "yaml":
                try:
                    import yaml
                except ImportError as exc:  # pragma: no cover
                    raise SerializationError("PyYAML required for yaml format") from exc
                data = yaml.safe_load(raw)
            else:
                raise SerializationError(f"unsupported format: {fmt}")
            if not isinstance(data, dict):
                raise SerializationError("payload must be a mapping")
            return data
        except SerializationError:
            raise
        except Exception as exc:
            raise SerializationError(str(exc)) from exc


def dumps(obj: Any, *, fmt: str = "json") -> str:
    return ExperienceSerializer().dumps(obj, fmt=fmt)


def loads(raw: str, *, fmt: str = "json", kind: str | None = None) -> Any:
    return ExperienceSerializer().loads(raw, fmt=fmt, kind=kind)
