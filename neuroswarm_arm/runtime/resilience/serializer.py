"""RMRE serializer — JSON / YAML + schema migration."""

from __future__ import annotations

import json
from typing import Any, Mapping, TypeVar

from pydantic import BaseModel

from .exceptions import SerializationError
from .execution import AlternativeExecutionPlan, ExecutionSnapshot
from .models import ModelProfile, RecoveryRecord
from .policy import ResiliencePolicy
from .versioning import SCHEMA_VERSION, migrate_payload

T = TypeVar("T", bound=BaseModel)


class ResilienceSerializer:
    """Serialize / deserialize RMRE domain objects."""

    def dumps(self, obj: BaseModel, *, fmt: str = "json", kind: str | None = None) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind or type(obj).__name__,
            "data": obj.model_dump(mode="json"),
        }
        return self._encode(payload, fmt)

    def loads(self, raw: str, model: type[T], *, fmt: str = "json") -> T:
        payload = migrate_payload(self._decode(raw, fmt))
        data = payload.get("data", payload)
        return model.model_validate(data)

    def dumps_dict(self, obj: BaseModel, *, kind: str | None = None) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": kind or type(obj).__name__,
            "data": obj.model_dump(mode="json"),
        }

    def loads_dict(self, payload: Mapping[str, Any], model: type[T]) -> T:
        migrated = migrate_payload(payload)
        data = migrated.get("data", migrated)
        return model.model_validate(data)

    def dumps_profile(self, profile: ModelProfile, *, fmt: str = "json") -> str:
        return self.dumps(profile, fmt=fmt, kind="ModelProfile")

    def loads_profile(self, raw: str, *, fmt: str = "json") -> ModelProfile:
        return self.loads(raw, ModelProfile, fmt=fmt)

    def dumps_policy(self, policy: ResiliencePolicy, *, fmt: str = "json") -> str:
        return self.dumps(policy, fmt=fmt, kind="ResiliencePolicy")

    def loads_policy(self, raw: str, *, fmt: str = "json") -> ResiliencePolicy:
        return self.loads(raw, ResiliencePolicy, fmt=fmt)

    def dumps_plan(self, plan: AlternativeExecutionPlan, *, fmt: str = "json") -> str:
        return self.dumps(plan, fmt=fmt, kind="AlternativeExecutionPlan")

    def loads_plan(self, raw: str, *, fmt: str = "json") -> AlternativeExecutionPlan:
        return self.loads(raw, AlternativeExecutionPlan, fmt=fmt)

    def dumps_snapshot(self, snap: ExecutionSnapshot, *, fmt: str = "json") -> str:
        return self.dumps(snap, fmt=fmt, kind="ExecutionSnapshot")

    def loads_snapshot(self, raw: str, *, fmt: str = "json") -> ExecutionSnapshot:
        return self.loads(raw, ExecutionSnapshot, fmt=fmt)

    def dumps_record(self, record: RecoveryRecord, *, fmt: str = "json") -> str:
        return self.dumps(record, fmt=fmt, kind="RecoveryRecord")

    def loads_record(self, raw: str, *, fmt: str = "json") -> RecoveryRecord:
        return self.loads(raw, RecoveryRecord, fmt=fmt)

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
        except Exception as exc:
            raise SerializationError(f"decode failed: {exc}") from exc
        if not isinstance(data, dict):
            raise SerializationError("payload must be a mapping")
        return data
