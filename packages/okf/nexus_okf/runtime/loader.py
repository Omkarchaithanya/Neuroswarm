from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_okf.compiler.artifact_gen.bundle import read_bundle
from nexus_okf.internal.mmap_json import load_json
from nexus_okf.runtime.cache_manager import CacheManager


class ArtifactLoader:
    def __init__(self, artifact_dir: Path):
        self.artifact_dir = Path(artifact_dir)
        self._cache = CacheManager()
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        bundle = self.artifact_dir / "runtime_bundle.okfb"
        if bundle.exists():
            self._data = read_bundle(bundle)
        else:
            for name in [
                "knowledge_manifest.json",
                "graph.json",
                "document_index.json",
                "section_index.json",
                "alias_map.json",
                "keyword_index.json",
                "navigation_index.json",
                "reference_index.json",
                "summary_index.json",
                "mount_index.json",
                "metadata_index.json",
                "toc_index.json",
                "dependency_graph.json",
                "ontology.json",
            ]:
                path = self.artifact_dir / name
                if path.exists():
                    self._data[name] = load_json(path)
        return self._data

    def get(self, name: str, default: Any = None) -> Any:
        if not self._data:
            self.load()
        return self._data.get(name, default)

    @property
    def document_index(self) -> dict[str, Any]:
        return self.get("document_index.json") or {}

    @property
    def section_index(self) -> dict[str, Any]:
        return self.get("section_index.json") or {}

    @property
    def alias_map(self) -> dict[str, str]:
        return self.get("alias_map.json") or {}

    @property
    def graph(self) -> dict[str, Any]:
        return self.get("graph.json") or {"nodes": [], "edges": []}

    @property
    def keyword_index(self) -> dict[str, list[str]]:
        return self.get("keyword_index.json") or {}

    @property
    def mount_index(self) -> dict[str, list[str]]:
        return self.get("mount_index.json") or {}

    @property
    def summary_index(self) -> dict[str, Any]:
        return self.get("summary_index.json") or {}

    @property
    def reference_index(self) -> dict[str, Any]:
        return self.get("reference_index.json") or {}

    @property
    def navigation_index(self) -> dict[str, Any]:
        return self.get("navigation_index.json") or {}
