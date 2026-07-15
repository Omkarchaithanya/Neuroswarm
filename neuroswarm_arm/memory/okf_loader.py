from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
<<<<<<< HEAD
from typing import Any

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
import yaml


@dataclass(slots=True)
class OKFDocument:
    path: Path
    title: str
    body: str
    frontmatter: dict


class OKFLoader:
<<<<<<< HEAD
    """Legacy facade — prefer neuroswarm_arm.runtime.okf / okf.runtime.OKFRuntime."""

    def __init__(self, root: Path, runtime: Any | None = None):
        self.root = root
        self.runtime = runtime

    def load_index(self) -> OKFDocument:
        if self.runtime is not None:
            node = self.runtime.load_index()
            return OKFDocument(
                path=self.root / "index.md",
                title=getattr(node, "title", "index"),
                body=getattr(node, "summary", ""),
                frontmatter={"type": "index"},
            )
        return self._read(self.root / "index.md")

    def load_topic(self, relative_path: str) -> OKFDocument:
        if self.runtime is not None:
            node = self.runtime.load_topic(relative_path)
            return OKFDocument(
                path=self.root / relative_path,
                title=getattr(node, "title", relative_path),
                body=getattr(node, "summary", ""),
                frontmatter={"type": "concept"},
            )
=======
    def __init__(self, root: Path):
        self.root = root

    def load_index(self) -> OKFDocument:
        path = self.root / "index.md"
        return self._read(path)

    def load_topic(self, relative_path: str) -> OKFDocument:
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
        return self._read(self.root / relative_path)

    def _read(self, path: Path) -> OKFDocument:
        raw = path.read_text(encoding="utf-8")
<<<<<<< HEAD
        frontmatter: dict = {}
=======
        frontmatter = {}
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
        body = raw
        if raw.startswith("---"):
            _, fm, body = raw.split("---", 2)
            frontmatter = yaml.safe_load(fm) or {}
        title = frontmatter.get("title") or path.stem
        return OKFDocument(path=path, title=title, body=body.strip(), frontmatter=frontmatter)
<<<<<<< HEAD
=======

>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
