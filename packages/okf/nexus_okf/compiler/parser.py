# Origin: NEXUS Extension
"""NEXUS compiler parser — builds on official Concept ID; preserves NEXUS aliases."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from nexus_okf.compiler.ast import DocumentNode, LinkNode, SectionNode
from nexus_okf.internal.hashutil import content_hash
from nexus_okf.official.parse import concept_id as official_concept_id
from nexus_okf.official.parse import split_frontmatter
from nexus_okf.official.reserved import RESERVED_FILENAMES, is_reserved

RESERVED = RESERVED_FILENAMES
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\-\s]", "", text).strip().lower()
    return re.sub(r"\s+", "-", s) or "section"


def _token_estimate(text: str) -> int:
    return max(1, len(text.split()))


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    fm, body, has_fm = split_frontmatter(raw)
    if not has_fm:
        return {}, raw
    return fm, body


def parse_sections(body: str) -> list[SectionNode]:
    matches = list(HEADING_RE.finditer(body))
    if not matches:
        return [
            SectionNode(
                id="body",
                title="Body",
                level=1,
                start_line=1,
                end_line=body.count("\n") + 1,
                text=body,
                token_estimate=_token_estimate(body),
            )
        ]
    lines = body.splitlines()
    sections: list[SectionNode] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = body[: m.start()].count("\n")
        end = body[: matches[i + 1].start()].count("\n") if i + 1 < len(matches) else len(lines)
        text = "\n".join(lines[start:end]).strip()
        sections.append(
            SectionNode(
                id=_slug(title),
                title=title,
                level=level,
                start_line=start + 1,
                end_line=end,
                text=text,
                token_estimate=_token_estimate(text),
            )
        )
    return sections


def parse_links(body: str) -> list[LinkNode]:
    links: list[LinkNode] = []
    for m in MD_LINK_RE.finditer(body):
        target = m.group(2).strip()
        section = None
        if "#" in target:
            target, section = target.split("#", 1)
        if (
            target.startswith(("http://", "https://", "mcp://"))
            or target.endswith((".md", ".yaml", ".yml"))
            or target.startswith(("./", "../", "/"))
            or "/" in target
        ):
            links.append(LinkNode(text=m.group(1), target=target, kind="md", section=section))
    # Wikilinks = NEXUS extension (not official OKF)
    for m in WIKI_LINK_RE.finditer(body):
        target = m.group(1).strip()
        section = None
        if "#" in target:
            target, section = target.split("#", 1)
        links.append(LinkNode(text=target, target=target, kind="wiki", section=section))
    return links


def parse_file(path: Path, root: Path) -> DocumentNode:
    """Parse for NEXUS compiler.

    Official Concept ID = path without .md.
    Optional frontmatter ``id`` becomes a NEXUS alias (stored in frontmatter; primary id is official).
    Does NOT invent a default ``type`` for non-reserved concepts (official conformance).
    Reserved index/log may lack type.
    """
    raw = path.read_text(encoding="utf-8")
    fm, body, has_fm = split_frontmatter(raw)
    if not has_fm:
        body = raw
    rel = path.relative_to(root).as_posix()
    reserved = is_reserved(path.name)
    official_id = official_concept_id(rel)

    # Preserve NEXUS alias id in frontmatter; primary DocumentNode.id = official Concept ID
    nexus_alias = fm.get("id")
    if nexus_alias and str(nexus_alias) != official_id:
        aliases = list(fm.get("aliases") or [])
        if str(nexus_alias) not in aliases:
            aliases.append(str(nexus_alias))
        fm = dict(fm)
        fm["aliases"] = aliases
        fm["nexus_id"] = str(nexus_alias)

    if reserved:
        doc_type = str(fm.get("type") or ("index" if path.name == "index.md" else "log"))
    else:
        # No auto-default: empty type stays empty so official/NEXUS validators can catch it
        doc_type = str(fm.get("type") or "")

    title = str(fm.get("title") or path.stem.replace("-", " ").title())
    return DocumentNode(
        path=path,
        rel_path=rel,
        frontmatter=fm,
        body=body,
        id=official_id,
        doc_type=doc_type,
        title=title,
        sections=parse_sections(body),
        links=parse_links(body),
        reserved=reserved,
        checksum=content_hash(raw),
        raw=raw,
    )


def discover_markdown(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if ".okf" not in p.parts)
