from __future__ import annotations

"""Synthetic scale harness for OKF compile (100 → 100k docs)."""

import time
from pathlib import Path

from nexus_okf.compiler.pipeline import compile_bundle


def generate_corpus(root: Path, n: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text(
        "---\ntype: index\nid: scale.index\ntitle: Scale Index\nokf_version: \"1.0\"\n---\n# Scale\n",
        encoding="utf-8",
    )
    for i in range(n):
        path = root / f"doc-{i:06d}.md"
        path.write_text(
            f"---\ntype: concept\nid: scale.doc.{i}\ntitle: Doc {i}\ntags: [scale, doc]\n"
            f"priority: {(i % 100)}\nokf_version: \"1.0\"\n---\n# Doc {i}\n\nBody for document {i}.\n",
            encoding="utf-8",
        )


def bench_scale(n: int, work: Path) -> dict:
    src = work / f"corp-{n}"
    art = work / f"art-{n}"
    generate_corpus(src, n)
    t0 = time.perf_counter()
    result = compile_bundle(src, art, strict=False, incremental=False)
    return {"n": n, "docs": result.docs_count, "compile_s": time.perf_counter() - t0, "ok": result.ok}


if __name__ == "__main__":
    import json
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    print(json.dumps(bench_scale(n, Path("work/okf/scale")), indent=2))
