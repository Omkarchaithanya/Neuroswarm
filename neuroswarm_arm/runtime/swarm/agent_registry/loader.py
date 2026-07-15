"""Load agents from YAML / JSON / dict (no remote download)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent import Agent
from .exceptions import SerializationError, ValidationError
from .serializer import AgentSerializer


class AgentLoader:
    """Load Agent definitions from files or in-memory payloads."""

    def __init__(self) -> None:
        self._ser = AgentSerializer()

    def from_dict(self, data: dict[str, Any]) -> Agent:
        try:
            return Agent.model_validate(data)
        except Exception as exc:
            raise ValidationError(f"invalid agent payload: {exc}") from exc

    def from_dicts(self, items: list[dict[str, Any]]) -> list[Agent]:
        return [self.from_dict(item) for item in items]

    def from_json_bytes(self, data: bytes) -> Agent | list[Agent]:
        try:
            import orjson

            obj = orjson.loads(data)
        except ImportError:
            import json

            obj = json.loads(data.decode("utf-8"))
        return self._from_obj(obj)

    def from_yaml_bytes(self, data: bytes) -> Agent | list[Agent]:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SerializationError("pyyaml required") from exc
        obj = yaml.safe_load(data.decode("utf-8"))
        return self._from_obj(obj)

    def from_file(self, path: str | Path) -> Agent | list[Agent]:
        p = Path(path)
        raw = p.read_bytes()
        suffix = p.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return self.from_yaml_bytes(raw)
        if suffix == ".json":
            return self.from_json_bytes(raw)
        # try JSON then YAML
        try:
            return self.from_json_bytes(raw)
        except Exception:
            return self.from_yaml_bytes(raw)

    def from_directory(self, path: str | Path) -> list[Agent]:
        root = Path(path)
        agents: list[Agent] = []
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            loaded = self.from_file(p)
            if isinstance(loaded, list):
                agents.extend(loaded)
            else:
                agents.append(loaded)
        return agents

    def _from_obj(self, obj: Any) -> Agent | list[Agent]:
        if isinstance(obj, list):
            return [self.from_dict(x) for x in obj]
        if isinstance(obj, dict):
            if "agents" in obj and isinstance(obj["agents"], list):
                return [self.from_dict(x) for x in obj["agents"]]
            return self.from_dict(obj)
        raise SerializationError("expected mapping or list of agents")
