from __future__ import annotations

from pathlib import Path

from nexus_okf.migration.google_okf_import import migrate_tree


def migrate_v0_to_v1(root: Path) -> int:
    return migrate_tree(root)
