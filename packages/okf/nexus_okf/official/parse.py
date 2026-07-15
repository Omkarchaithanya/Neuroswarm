# Origin: Official OKF
"""Official OKF document parse — SPEC.md §2 Concept ID, §4 frontmatter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from nexus_okf.official.links import OfficialLink, parse_markdown_links
from nexus_okf.official.reserved import is_reserved, is_root_index


@dataclass(slots=True)
class OfficialDocument:
    path: Path
    rel_path: str
    concept_id: str
    reserved: bool
    frontmatter: dict[str, Any]
    body: str
    has_frontmatter: bool
    links: list[OfficialLink] = field(default_factory=list)
    raw: str = ""


def concept_id(rel_path: str) -> str:
    """SPEC §2: path within bundle with .md suffix removed."""
    p = rel_path.replace("\\", "/")
    if p.endswith(".md"):
        p = p[: -len(".md")]
    return p


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str, bool]:
    """Return (frontmatter, body, has_frontmatter_block)."""
    if not raw.startswith("---"):
        return {}, raw, False
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw, False
    fm = yaml.safe_load(parts[1]) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, parts[2].lstrip("\n"), True


def parse_document(path: Path, bundle_root: Path) -> OfficialDocument:
    raw = path.read_text(encoding="utf-8")
    rel = path.relative_to(bundle_root).as_posix()
    reserved = is_reserved(path.name)
    fm, body, has_fm = split_frontmatter(raw)

    # SPEC §6: index.md has no frontmatter except root may declare okf_version (§11)
    if reserved and path.name == "index.md":
        if is_root_index(rel) and has_fm:
            # Only okf_version permitted in root index frontmatter
            allowed = {k: v for k, v in fm.items() if k == "okf_version"}
            # Keep parse of full FM for validation to detect illegal keys
            pass
        elif has_fm and not is_root_index(rel):
            # Nested index should have no FM — keep fm for validator
            pass

    return OfficialDocument(
        path=path,
        rel_path=rel,
        concept_id=concept_id(rel),
        reserved=reserved,
        frontmatter=fm,
        body=body if has_fm else raw,
        has_frontmatter=has_fm,
        links=parse_markdown_links(body if has_fm else raw),
        raw=raw,
    )


def discover_markdown(bundle_root: Path) -> list[Path]:
    return sorted(
        p
        for p in bundle_root.rglob("*.md")
        if ".okf" not in p.parts and p.is_file()
    )
