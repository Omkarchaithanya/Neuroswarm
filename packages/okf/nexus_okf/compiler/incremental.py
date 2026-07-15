from __future__ import annotations

from pathlib import Path

from nexus_okf.compiler.cache import BuildCache
from nexus_okf.internal.hashutil import content_hash


def compute_dirty(
    paths: list[Path],
    source_root: Path,
    cache: BuildCache,
    compiler_version: str,
) -> set[str]:
    dirty: set[str] = set()
    for path in paths:
        rel = path.relative_to(source_root).as_posix()
        digest = cache.key(rel, path.read_bytes(), "1.0", compiler_version)
        if not cache.hit(rel, digest):
            dirty.add(rel)
    # if no prior index, everything dirty
    if not cache.index:
        return {p.relative_to(source_root).as_posix() for p in paths}
    return dirty


def expand_dirty_with_deps(dirty: set[str], dependency_graph: dict) -> set[str]:
    """Expand dirty set using reverse edges from dependency_graph artifact."""
    reverse: dict[str, list[str]] = {}
    # dependency_graph uses doc ids; callers may map path->id separately
    for e in dependency_graph.get("edges") or []:
        reverse.setdefault(e.get("to"), []).append(e.get("from"))
    out = set(dirty)
    stack = list(dirty)
    while stack:
        cur = stack.pop()
        for parent in reverse.get(cur, []):
            if parent not in out:
                out.add(parent)
                stack.append(parent)
    return out
