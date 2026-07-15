from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from nexus_okf.internal.hashutil import content_hash
from nexus_okf.internal.mmap_json import load_json


def write_bundle(artifact_dir: Path, names: list[str] | None = None) -> Path:
    """Pack key JSON artifacts into a single .okfb (length-prefixed JSON blobs)."""
    names = names or [
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
    ]
    out = artifact_dir / "runtime_bundle.okfb"
    parts: list[tuple[str, bytes]] = []
    for name in names:
        path = artifact_dir / name
        if path.exists():
            parts.append((name, path.read_bytes()))
    with out.open("wb") as f:
        f.write(b"OKFB")
        f.write(struct.pack("<I", len(parts)))
        for name, data in parts:
            nb = name.encode("utf-8")
            f.write(struct.pack("<I", len(nb)))
            f.write(nb)
            f.write(struct.pack("<I", len(data)))
            f.write(data)
    return out


def read_bundle(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:4] != b"OKFB":
        raise ValueError("Invalid OKF bundle magic")
    offset = 4
    (count,) = struct.unpack_from("<I", data, offset)
    offset += 4
    out: dict[str, Any] = {}
    for _ in range(count):
        (nlen,) = struct.unpack_from("<I", data, offset)
        offset += 4
        name = data[offset : offset + nlen].decode("utf-8")
        offset += nlen
        (dlen,) = struct.unpack_from("<I", data, offset)
        offset += 4
        blob = data[offset : offset + dlen]
        offset += dlen
        try:
            import orjson

            out[name] = orjson.loads(blob)
        except ImportError:
            out[name] = json.loads(blob.decode("utf-8"))
    return out


def bundle_checksum(path: Path) -> str:
    return content_hash(path.read_bytes())
