# Origin: Official OKF
"""Reserved filenames per Google OKF SPEC.md §3.1."""

from __future__ import annotations

RESERVED_FILENAMES = frozenset({"index.md", "log.md"})


def is_reserved(name: str) -> bool:
    return name in RESERVED_FILENAMES


def is_root_index(rel_path: str) -> bool:
    return rel_path == "index.md" or rel_path.replace("\\", "/") == "index.md"
