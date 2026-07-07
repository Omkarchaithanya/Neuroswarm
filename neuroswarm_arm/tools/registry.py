from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import yaml

from ..schemas import ToolDef


@dataclass
class ToolRegistry:
    tools: dict[str, ToolDef] = field(default_factory=dict)

    def register(self, tool: ToolDef) -> None:
        self.tools[tool.id] = tool

    def load_okf_metadata(self, root: Path) -> None:
        for meta in root.rglob("okf-metadata.yaml"):
            data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
            self.register(
                ToolDef(
                    id=str(data.get("id") or meta.parent.name),
                    name=str(data.get("name") or meta.parent.name),
                    description=str(data.get("description") or ""),
                    params=dict(data.get("params") or {}),
                    endpoint=data.get("endpoint"),
                    auth=data.get("auth"),
                )
            )

    def as_list(self) -> list[ToolDef]:
        return list(self.tools.values())

