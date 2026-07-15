<<<<<<< HEAD
"""Tool registry facade — delegates to runtime.router when bound."""

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
<<<<<<< HEAD

import yaml

from neuroswarm_arm.runtime.router.models import ToolRecord
from neuroswarm_arm.runtime.router.registry import ToolRegistry as RuntimeToolRegistry
from neuroswarm_arm.schemas import ToolDef


def _to_def(record: ToolRecord | ToolDef) -> ToolDef:
    if isinstance(record, ToolDef):
        return record
    return ToolDef(
        id=record.id,
        name=record.name,
        description=record.description,
        params=dict(record.params),
        endpoint=record.endpoint,
        auth=record.auth,
    )


def _to_record(tool: ToolDef | ToolRecord | dict) -> ToolRecord:
    if isinstance(tool, ToolRecord):
        return tool
    if isinstance(tool, ToolDef):
        return ToolRecord(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            params=dict(tool.params),
            endpoint=tool.endpoint,
            auth=tool.auth,
        )
    return ToolRecord.from_dict(tool)
=======
import yaml

from ..schemas import ToolDef
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84


@dataclass
class ToolRegistry:
    tools: dict[str, ToolDef] = field(default_factory=dict)
<<<<<<< HEAD
    _runtime: RuntimeToolRegistry | None = field(default=None, repr=False)

    def bind(self, runtime: RuntimeToolRegistry) -> RuntimeToolRegistry:
        self._runtime = runtime
        self._sync_from_runtime()
        return runtime

    def _sync_from_runtime(self) -> None:
        if self._runtime is None:
            return
        self.tools = {t.id: _to_def(t) for t in self._runtime.as_list()}

    def register(self, tool: ToolDef | ToolRecord | dict) -> None:
        record = _to_record(tool)
        if self._runtime is not None:
            self._runtime.register(record)
            self._sync_from_runtime()
            return
        self.tools[record.id] = _to_def(record)

    def load_okf_metadata(self, root: Path) -> None:
        if self._runtime is not None:
            from neuroswarm_arm.runtime.router.registry_loader import RegistryLoader

            loader = RegistryLoader()
            self._runtime.bulk_register(loader.load_path(root))
            self._sync_from_runtime()
            return
        for meta in Path(root).rglob("okf-metadata.yaml"):
=======

    def register(self, tool: ToolDef) -> None:
        self.tools[tool.id] = tool

    def load_okf_metadata(self, root: Path) -> None:
        for meta in root.rglob("okf-metadata.yaml"):
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
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
<<<<<<< HEAD
        if self._runtime is not None:
            self._sync_from_runtime()
        return list(self.tools.values())
=======
        return list(self.tools.values())

>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
