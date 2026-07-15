"""Serialize / deserialize SwarmTemplate and registry snapshots (JSON, YAML)."""

from __future__ import annotations

from typing import Any, Literal

from .exceptions import SerializationError
from .template import SwarmTemplate
from .versioning import SCHEMA_VERSION, migrate

Format = Literal["json", "yaml"]


class SwarmSerializer:
    """Multi-format template / snapshot persistence."""

    def dumps_template(self, template: SwarmTemplate, *, fmt: Format = "json") -> bytes:
        payload = template.model_dump(mode="json")
        payload["schema_version"] = SCHEMA_VERSION
        payload["_content_hash"] = template.content_hash()
        return self._encode(payload, fmt)

    def loads_template(self, data: bytes, *, fmt: Format = "json") -> SwarmTemplate:
        payload = migrate(self._decode(data, fmt))
        payload.pop("schema_version", None)
        payload.pop("_content_hash", None)
        return SwarmTemplate.model_validate(payload)

    def dumps_registry(
        self,
        templates: list[SwarmTemplate],
        *,
        fmt: Format = "json",
        meta: dict[str, Any] | None = None,
    ) -> bytes:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "templates": [t.model_dump(mode="json") for t in templates],
            "meta": dict(meta or {}),
        }
        return self._encode(payload, fmt)

    def loads_registry(self, data: bytes, *, fmt: Format = "json") -> list[SwarmTemplate]:
        payload = migrate(self._decode(data, fmt))
        raw = payload.get("templates", [])
        if not isinstance(raw, list):
            raise SerializationError("templates must be a list")
        return [SwarmTemplate.model_validate(t) for t in raw]

    def _encode(self, payload: dict[str, Any], fmt: Format) -> bytes:
        if fmt == "json":
            try:
                import orjson

                return orjson.dumps(payload)
            except ImportError:
                import json

                return json.dumps(payload, default=str).encode("utf-8")
        if fmt == "yaml":
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise SerializationError("pyyaml required for YAML") from exc
            return yaml.safe_dump(payload, sort_keys=True).encode("utf-8")
        raise SerializationError(f"unknown format: {fmt}")

    def _decode(self, data: bytes, fmt: Format) -> dict[str, Any]:
        if fmt == "json":
            try:
                import orjson

                obj = orjson.loads(data)
            except ImportError:
                import json

                obj = json.loads(data.decode("utf-8"))
            if not isinstance(obj, dict):
                raise SerializationError("expected JSON object")
            return obj
        if fmt == "yaml":
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise SerializationError("pyyaml required for YAML") from exc
            obj = yaml.safe_load(data.decode("utf-8"))
            if not isinstance(obj, dict):
                raise SerializationError("expected YAML mapping")
            return obj
        raise SerializationError(f"unknown format: {fmt}")


def dumps(template: SwarmTemplate, *, fmt: Format = "json") -> bytes:
    return SwarmSerializer().dumps_template(template, fmt=fmt)


def loads(data: bytes, *, fmt: Format = "json") -> SwarmTemplate:
    return SwarmSerializer().loads_template(data, fmt=fmt)
