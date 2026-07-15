from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LinkNode:
    text: str
    target: str
    kind: str = "md"
    section: str | None = None


@dataclass(slots=True)
class SectionNode:
    id: str
    title: str
    level: int
    start_line: int
    end_line: int
    text: str
    token_estimate: int = 0


@dataclass(slots=True)
class DocumentNode:
    path: Path
    rel_path: str
    frontmatter: dict[str, Any]
    body: str
    id: str
    doc_type: str
    title: str
    sections: list[SectionNode] = field(default_factory=list)
    links: list[LinkNode] = field(default_factory=list)
    reserved: bool = False
    checksum: str = ""
    raw: str = ""
