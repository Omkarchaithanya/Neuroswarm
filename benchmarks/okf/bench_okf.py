"""OKF compile/query microbenchmark."""

from __future__ import annotations

import time
from pathlib import Path

from nexus_okf.compiler.pipeline import compile_bundle
from nexus_okf.runtime.kernel import build_runtime
from nexus_okf.runtime.query import OKFQuery


def run(n_docs: int = 100, out_dir: Path | None = None) -> dict:
    root = Path(__file__).resolve().parents[2] / "okf"
    art = (out_dir or Path("work/okf/bench")) / f"n{n_docs}"
    t0 = time.perf_counter()
    result = compile_bundle(root, art / "artifacts", strict=False)
    compile_s = time.perf_counter() - t0
    rt = build_runtime(art / "artifacts", root)
    lat = []
    for i in range(20):
        t1 = time.perf_counter()
        rt.query(OKFQuery(text=f"policy budget tool github {i}", agent_profile="architect", token_budget=400))
        lat.append((time.perf_counter() - t1) * 1000)
    lat.sort()
    return {
        "n_docs_corpus": result.docs_count,
        "requested_scale": n_docs,
        "compile_s": compile_s,
        "query_p50_ms": lat[len(lat) // 2],
        "query_p99_ms": lat[-1],
        "cache": rt.metrics.snapshot(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
