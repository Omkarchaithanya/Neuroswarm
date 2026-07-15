from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_okf.internal.hashutil import content_hash, file_hash
from nexus_okf.internal.mmap_json import dump_json


def write_manifest(
    artifact_dir: Path,
    *,
    docs_count: int,
    compiler_version: str,
    artifact_paths: dict[str, Path],
    diagnostics: dict[str, Any],
) -> Path:
    artifacts = {name: {"path": p.name, "checksum": file_hash(p)} for name, p in artifact_paths.items() if p.exists()}
    manifest = {
        "okf_version": "1.0",
        "compiler_version": compiler_version,
        "docs_count": docs_count,
        "artifacts": artifacts,
        "diagnostics": diagnostics,
        "bundle_id": content_hash(str(sorted(artifacts.items())).encode()),
    }
    path = artifact_dir / "knowledge_manifest.json"
    dump_json(path, manifest)
    return path
