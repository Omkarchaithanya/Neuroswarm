# Origin: Official OKF + NEXUS Extension (split helpers)
"""Migration helpers.

Official: ensure concept docs have ``type`` only.
NEXUS: optional alias enrichment (separate entrypoint).
"""

from __future__ import annotations

from pathlib import Path

from nexus_okf.official.reserved import is_reserved


def migrate_official(root: Path) -> int:
    """Make a Google-style bundle §9-conformant: add minimal ``type`` if missing.

    Does not invent NEXUS ``id`` / ``okf_version`` on concepts.
    Skips reserved index.md / log.md.
    """
    count = 0
    for path in root.rglob("*.md"):
        if ".okf" in path.parts or is_reserved(path.name):
            continue
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            title = path.stem.replace("-", " ").title()
            wrapped = f"---\ntype: concept\ntitle: {title}\n---\n{raw}"
            path.write_text(wrapped, encoding="utf-8")
            count += 1
            continue
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        fm = parts[1]
        if "type:" not in fm:
            path.write_text(f"---\ntype: concept\n{fm.lstrip()}---{parts[2]}", encoding="utf-8")
            count += 1
    return count


def migrate_tree(root: Path) -> int:
    """NEXUS convenience migrate: official type fix + optional nexus_id alias.

    Prefer ``migrate_official`` for pure Google conformance.
    """
    count = migrate_official(root)
    for path in root.rglob("*.md"):
        if ".okf" in path.parts or is_reserved(path.name):
            continue
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            continue
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        fm = parts[1]
        if "id:" in fm:
            continue
        rel = path.relative_to(root).as_posix().removesuffix(".md")
        # NEXUS alias only — official Concept ID remains path
        path.write_text(
            f"---\nid: {rel.replace('/', '.')}\n{fm.lstrip()}---{parts[2]}",
            encoding="utf-8",
        )
        count += 1
    return count
