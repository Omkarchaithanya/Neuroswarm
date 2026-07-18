from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from nexus_okf.compiler.ast import DocumentNode, LinkNode, SectionNode
from nexus_okf.internal.hashutil import content_hash


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _doc_to_dict(doc: DocumentNode) -> dict:
    payload = asdict(doc)
    payload["path"] = str(doc.path)
    return _jsonable(payload)


def _doc_from_dict(payload: dict) -> DocumentNode:
    sections = [SectionNode(**s) for s in payload.get("sections") or []]
    links = [LinkNode(**link) for link in payload.get("links") or []]
    return DocumentNode(
        path=Path(payload["path"]),
        rel_path=payload["rel_path"],
        frontmatter=dict(payload.get("frontmatter") or {}),
        body=payload.get("body") or "",
        id=payload["id"],
        doc_type=payload.get("doc_type") or "",
        title=payload.get("title") or "",
        sections=sections,
        links=links,
        reserved=bool(payload.get("reserved")),
        checksum=payload.get("checksum") or "",
        raw=payload.get("raw") or "",
    )


class BuildCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.docs_root = self.root / "docs"
        self.docs_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "cache_index.json"
        self.index: dict[str, str] = {}
        if self.index_path.exists():
            self.index = json.loads(self.index_path.read_text(encoding="utf-8"))

    def key(self, rel: str, data: bytes, schema_ver: str, compiler_ver: str) -> str:
        return content_hash(rel.encode() + b"|" + data + schema_ver.encode() + compiler_ver.encode())

    def hit(self, rel: str, digest: str) -> bool:
        return self.index.get(rel) == digest

    def put(self, rel: str, digest: str) -> None:
        self.index[rel] = digest

    def _doc_path(self, rel: str) -> Path:
        safe = rel.replace("/", "__")
        return self.docs_root / f"{safe}.json"

    def has_doc(self, rel: str, digest: str) -> bool:
        return self.hit(rel, digest) and self._doc_path(rel).exists()

    def load_doc(self, rel: str) -> DocumentNode | None:
        path = self._doc_path(rel)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _doc_from_dict(payload)

    def store_doc(self, rel: str, doc: DocumentNode, digest: str) -> None:
        self.put(rel, digest)
        self._doc_path(rel).write_text(
            json.dumps(_doc_to_dict(doc), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def save(self) -> None:
        self.index_path.write_text(json.dumps(self.index, indent=2, sort_keys=True), encoding="utf-8")
