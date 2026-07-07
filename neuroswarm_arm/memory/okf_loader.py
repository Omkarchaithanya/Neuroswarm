from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass(slots=True)
class OKFDocument:
    path: Path
    title: str
    body: str
    frontmatter: dict


class OKFLoader:
    def __init__(self, root: Path):
        self.root = root

    def load_index(self) -> OKFDocument:
        path = self.root / "index.md"
        return self._read(path)

    def load_topic(self, relative_path: str) -> OKFDocument:
        return self._read(self.root / relative_path)

    def _read(self, path: Path) -> OKFDocument:
        raw = path.read_text(encoding="utf-8")
        frontmatter = {}
        body = raw
        if raw.startswith("---"):
            _, fm, body = raw.split("---", 2)
            frontmatter = yaml.safe_load(fm) or {}
        title = frontmatter.get("title") or path.stem
        return OKFDocument(path=path, title=title, body=body.strip(), frontmatter=frontmatter)

