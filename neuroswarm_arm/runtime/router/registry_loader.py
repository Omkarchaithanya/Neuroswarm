"""Load tools from YAML, JSON, Markdown frontmatter, OKF metadata."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

import yaml

from .models import ToolRecord


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(value)]


def record_from_mapping(data: dict[str, Any], *, okf_path: str | None = None) -> ToolRecord:
    params = dict(data.get("params") or {})
    input_schema = dict(data.get("input_schema") or {})
    if not input_schema and params:
        input_schema = {
            "type": "object",
            "properties": {k: {"type": "string", "description": str(v)} for k, v in params.items()},
        }
    tool_id = str(data.get("id") or data.get("name") or "unknown")
    return ToolRecord(
        id=tool_id,
        name=str(data.get("name") or tool_id),
        description=str(data.get("description") or ""),
        namespace=str(data.get("namespace") or "default"),
        version=str(data.get("version") or "1.0.0"),
        category=str(data.get("category") or "general"),
        capabilities=_as_list(data.get("capabilities")),
        dependencies=_as_list(data.get("dependencies")),
        permissions=_as_list(data.get("permissions")),
        rate_limits={str(k): float(v) for k, v in dict(data.get("rate_limits") or {}).items()},
        cost_usd=float(data.get("cost_usd") or data.get("cost") or 0.0),
        p50_latency_ms=float(data.get("p50_latency_ms") or data.get("latency_ms") or 50.0),
        tags=_as_list(data.get("tags")),
        params={str(k): str(v) for k, v in params.items()},
        input_schema=input_schema,
        output_schema=dict(data.get("output_schema") or {}),
        example_prompts=_as_list(data.get("example_prompts") or data.get("examples")),
        example_args=dict(data.get("example_args") or {}),
        endpoint=data.get("endpoint"),
        auth=data.get("auth"),
        okf_path=okf_path or data.get("okf_path"),
        popularity=float(data.get("popularity") or 0.0),
        success_rate=float(data.get("success_rate") if data.get("success_rate") is not None else 1.0),
        failure_rate=float(data.get("failure_rate") or 0.0),
        recent_usage=float(data.get("recent_usage") or 0.0),
        reliability=float(data.get("reliability") if data.get("reliability") is not None else 1.0),
        agent_roles=_as_list(data.get("agent_roles")),
        workflow_stages=_as_list(data.get("workflow_stages")),
    )


def load_yaml_tool(path: Path) -> ToolRecord:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML tool must be mapping: {path}")
    return record_from_mapping(data, okf_path=str(path))


def load_json_tool(path: Path) -> ToolRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON tool must be object: {path}")
    return record_from_mapping(data, okf_path=str(path))


def load_markdown_tool(path: Path) -> ToolRecord:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2).strip()
    else:
        meta = {}
        body = text.strip()
    if not isinstance(meta, dict):
        meta = {}
    if body and not meta.get("description"):
        meta["description"] = body.split("\n\n", 1)[0][:2000]
    if not meta.get("id"):
        meta["id"] = path.stem
    if not meta.get("name"):
        meta["name"] = path.stem
    return record_from_mapping(meta, okf_path=str(path))


def load_okf_metadata_file(path: Path) -> ToolRecord:
    return load_yaml_tool(path)


class RegistryLoader:
    def load_path(self, path: Path) -> list[ToolRecord]:
        path = Path(path)
        if path.is_file():
            return [self.load_file(path)]
        tools: list[ToolRecord] = []
        for meta in path.rglob("okf-metadata.yaml"):
            tools.append(load_okf_metadata_file(meta))
        for yml in path.rglob("*.tool.yaml"):
            tools.append(load_yaml_tool(yml))
        for js in path.rglob("*.tool.json"):
            tools.append(load_json_tool(js))
        for md in path.rglob("*.tool.md"):
            tools.append(load_markdown_tool(md))
        # Deduplicate by id (last wins)
        by_id = {t.id: t for t in tools}
        return list(by_id.values())

    def load_file(self, path: Path) -> ToolRecord:
        path = Path(path)
        suffix = path.suffix.lower()
        name = path.name.lower()
        if name == "okf-metadata.yaml" or suffix in {".yaml", ".yml"}:
            return load_yaml_tool(path)
        if suffix == ".json":
            return load_json_tool(path)
        if suffix == ".md":
            return load_markdown_tool(path)
        raise ValueError(f"unsupported tool file: {path}")
