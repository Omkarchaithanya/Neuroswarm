from __future__ import annotations

from pathlib import Path
from typing import Any


def write_evolved_prompt(source_root: Path, rel_path: str, body: str, frontmatter: dict[str, Any] | None = None) -> Path:
    """Evolution loop writes back to OKF *sources* only — never artifacts."""
    import yaml

    path = Path(source_root) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = frontmatter or {"type": "agent", "title": path.stem, "okf_version": "1.0"}
    text = "---\n" + yaml.safe_dump(fm, sort_keys=True) + "---\n" + body
    path.write_text(text, encoding="utf-8")
    return path
