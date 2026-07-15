from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_okf.internal.mmap_json import dump_json


def write_graph(artifact_dir: Path, graph: dict[str, Any]) -> Path:
    path = artifact_dir / "graph.json"
    dump_json(path, graph)
    return path


def write_ontology(artifact_dir: Path, ontology: dict[str, Any]) -> Path:
    path = artifact_dir / "ontology.json"
    dump_json(path, ontology)
    return path
