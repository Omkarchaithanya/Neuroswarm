"""Serialize / deserialize Agent and registry snapshots (JSON, YAML)."""

from __future__ import annotations

from typing import Any, Literal

from .agent import Agent
from .exceptions import SerializationError

SCHEMA_VERSION = 1
Format = Literal["json", "yaml"]


def _migrate(payload: dict[str, Any]) -> dict[str, Any]:
    version = int(payload.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise SerializationError(
            f"unsupported schema_version {version} (max {SCHEMA_VERSION})"
        )
    if version < 1:
        payload["schema_version"] = 1
    payload["schema_version"] = SCHEMA_VERSION
    return payload


class AgentSerializer:
    """Multi-format agent / snapshot persistence."""

    def dumps_agent(self, agent: Agent, *, fmt: Format = "json") -> bytes:
        payload = agent.model_dump(mode="json")
        payload["schema_version"] = SCHEMA_VERSION
        payload["_content_hash"] = agent.content_hash()
        return self._encode(payload, fmt)

    def loads_agent(self, data: bytes, *, fmt: Format = "json") -> Agent:
        payload = _migrate(self._decode(data, fmt))
        payload.pop("schema_version", None)
        payload.pop("_content_hash", None)
        return Agent.model_validate(payload)

    def dumps_registry(
        self,
        agents: list[Agent],
        *,
        fmt: Format = "json",
        meta: dict[str, Any] | None = None,
    ) -> bytes:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "agents": [a.model_dump(mode="json") for a in agents],
            "meta": dict(meta or {}),
        }
        return self._encode(payload, fmt)

    def loads_registry(self, data: bytes, *, fmt: Format = "json") -> list[Agent]:
        payload = _migrate(self._decode(data, fmt))
        raw_agents = payload.get("agents", [])
        if not isinstance(raw_agents, list):
            raise SerializationError("agents must be a list")
        return [Agent.model_validate(a) for a in raw_agents]

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


def dumps(agent: Agent, *, fmt: Format = "json") -> bytes:
    return AgentSerializer().dumps_agent(agent, fmt=fmt)


def loads(data: bytes, *, fmt: Format = "json") -> Agent:
    return AgentSerializer().loads_agent(data, fmt=fmt)
