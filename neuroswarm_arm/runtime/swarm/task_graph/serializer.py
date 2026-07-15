"""Serialize / deserialize TaskGraph (JSON, YAML, MessagePack, Pickle)."""

from __future__ import annotations

import pickle
from typing import Any

from .enums import SerializationFormat
from .exceptions import SerializationError
from .graph import TaskGraph

SCHEMA_VERSION = 1


def _migrate(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade older schema versions to current."""
    version = int(payload.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise SerializationError(
            f"unsupported schema_version {version} (max {SCHEMA_VERSION})"
        )
    # v1 is current — placeholder for future migrations
    if version < 1:
        payload["schema_version"] = 1
    payload["schema_version"] = SCHEMA_VERSION
    return payload


class GraphSerializer:
    """Multi-format graph persistence."""

    def dumps(
        self,
        graph: TaskGraph,
        *,
        fmt: SerializationFormat = SerializationFormat.JSON,
    ) -> bytes:
        payload = graph.definition_payload()
        payload["schema_version"] = SCHEMA_VERSION
        # include full pydantic dump for round-trip fidelity
        full = graph.model_dump(mode="json")
        full["schema_version"] = SCHEMA_VERSION
        full["_definition_hash"] = graph.content_hash()

        if fmt is SerializationFormat.JSON:
            try:
                import orjson

                return orjson.dumps(full)
            except ImportError:
                import json

                return json.dumps(full, default=str).encode("utf-8")

        if fmt is SerializationFormat.YAML:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise SerializationError("pyyaml required for YAML") from exc
            return yaml.safe_dump(full, sort_keys=True).encode("utf-8")

        if fmt is SerializationFormat.MSGPACK:
            try:
                import msgpack
            except ImportError as exc:
                raise SerializationError(
                    "msgpack not installed; pip install msgpack"
                ) from exc
            return msgpack.packb(full, use_bin_type=True)

        if fmt is SerializationFormat.PICKLE:
            return pickle.dumps(full, protocol=pickle.HIGHEST_PROTOCOL)

        raise SerializationError(f"unknown format: {fmt}")

    def loads(
        self,
        data: bytes,
        *,
        fmt: SerializationFormat = SerializationFormat.JSON,
    ) -> TaskGraph:
        if fmt is SerializationFormat.JSON:
            try:
                import orjson

                payload = orjson.loads(data)
            except ImportError:
                import json

                payload = json.loads(data.decode("utf-8"))
        elif fmt is SerializationFormat.YAML:
            import yaml

            payload = yaml.safe_load(data.decode("utf-8"))
        elif fmt is SerializationFormat.MSGPACK:
            try:
                import msgpack
            except ImportError as exc:
                raise SerializationError(
                    "msgpack not installed; pip install msgpack"
                ) from exc
            payload = msgpack.unpackb(data, raw=False)
        elif fmt is SerializationFormat.PICKLE:
            payload = pickle.loads(data)  # noqa: S301 — trusted local only
        else:
            raise SerializationError(f"unknown format: {fmt}")

        if not isinstance(payload, dict):
            raise SerializationError("payload must be a mapping")
        payload.pop("_definition_hash", None)
        payload = _migrate(payload)
        # drop private / non-model keys
        payload.pop("_frozen", None)
        graph = TaskGraph.model_validate(payload)
        graph._frozen = False
        return graph

    def dump_pydantic(self, graph: TaskGraph) -> dict[str, Any]:
        return graph.model_dump(mode="json")

    def load_pydantic(self, data: dict[str, Any]) -> TaskGraph:
        data = _migrate(dict(data))
        graph = TaskGraph.model_validate(data)
        graph._frozen = False
        return graph


def dumps(graph: TaskGraph, *, fmt: SerializationFormat = SerializationFormat.JSON) -> bytes:
    return GraphSerializer().dumps(graph, fmt=fmt)


def loads(data: bytes, *, fmt: SerializationFormat = SerializationFormat.JSON) -> TaskGraph:
    return GraphSerializer().loads(data, fmt=fmt)
