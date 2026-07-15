# Origin: Official OKF
"""Markdown link helpers per Google OKF SPEC.md §5."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass(slots=True)
class OfficialLink:
    text: str
    target: str
    absolute: bool  # bundle-root absolute (/...)
    section: str | None = None


def parse_markdown_links(body: str) -> list[OfficialLink]:
    """Official OKF: standard markdown links only (no wikilinks)."""
    out: list[OfficialLink] = []
    for m in MD_LINK_RE.finditer(body):
        text = m.group(1)
        target = m.group(2).strip()
        section = None
        if "#" in target:
            target, section = target.split("#", 1)
        absolute = target.startswith("/")
        out.append(OfficialLink(text=text, target=target, absolute=absolute, section=section))
    return out


def resolve_link_target(from_rel: str, target: str, bundle_root: Path) -> Path | None:
    """Resolve to a path under bundle; return None if external or missing (not an error)."""
    if target.startswith(("http://", "https://", "mailto:")):
        return None
    clean = target.lstrip("/")
    if target.startswith("/"):
        cand = bundle_root / clean
    else:
        base = (bundle_root / from_rel).parent
        cand = (base / target).resolve()
        try:
            cand.relative_to(bundle_root.resolve())
        except ValueError:
            return None
    if cand.suffix == "" and cand.is_dir():
        return cand
    return cand if cand.exists() else None
