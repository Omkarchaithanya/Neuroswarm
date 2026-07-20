"""Active GEPA text artifacts loaded into chat/governor prompts."""

from __future__ import annotations

import json
import os
from pathlib import Path


def gepa_active_dir(work_dir: Path | None = None) -> Path:
    root = Path(work_dir or os.getenv("NSA_AROP_WORK", "work/arop"))
    return root / "gepa" / "active"


def load_active_system_prompt(*, work_dir: Path | None = None) -> str:
    """Return deployed GEPA system_prompt.md if present, else empty string."""
    path = gepa_active_dir(work_dir) / "system_prompt.md"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    # Strip optional YAML frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    return text.strip()


def activate_deployed_components(
    components: dict[str, str],
    *,
    work_dir: Path | None = None,
    teacher: str | None = None,
) -> list[str]:
    """Write component texts under work/arop/gepa/active/ for runtime load."""
    active = gepa_active_dir(work_dir)
    active.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, body in components.items():
        path = active / f"{name}.md"
        path.write_text(str(body or ""), encoding="utf-8")
        written.append(str(path))
    # Teacher honesty marker for smoke (http | mock | mock_fallback | …).
    inferred = teacher
    if not inferred:
        blob = "\n".join(str(v) for v in components.values())
        if "[GEPA lesson]:" in blob:
            inferred = "mock_fallback"
        else:
            inferred = "http"
    marker = active / "teacher.json"
    marker.write_text(json.dumps({"teacher": inferred}, indent=2), encoding="utf-8")
    written.append(str(marker))
    return written
