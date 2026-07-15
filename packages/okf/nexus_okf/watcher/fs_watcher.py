from __future__ import annotations

import time
from pathlib import Path

from nexus_okf.compiler.pipeline import compile_bundle


def watch_and_rebuild(source: Path, interval: float = 1.0) -> None:
    source = Path(source)
    last: dict[str, float] = {}
    print(f"watching {source} ...")
    while True:
        changed = False
        for path in source.rglob("*.md"):
            if ".okf" in path.parts:
                continue
            m = path.stat().st_mtime
            key = str(path)
            if key not in last or last[key] != m:
                last[key] = m
                changed = True
        if changed:
            result = compile_bundle(source, incremental=True)
            print(f"rebuild ok={result.ok} docs={result.docs_count} dirty={result.dirty_count}")
        time.sleep(interval)
