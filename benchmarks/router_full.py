"""Full router benchmark CLI."""

from __future__ import annotations

from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.common import DEFAULT_RESULTS_DIR, DEFAULT_TOOL_ROOT, build_router, evaluate_router, write_json
from neuroswarm_arm.runtime.router.benchmarks import write_benchmark


def main() -> None:
    result = evaluate_router(DEFAULT_TOOL_ROOT, top_k=3)
    out = DEFAULT_RESULTS_DIR / "router_full.json"
    write_json(out, result)
    if result.get("full"):
        write_benchmark(result["full"], DEFAULT_RESULTS_DIR / "router_accuracy.json")
    print(json.dumps({"wrote": str(out), "top3": result.get("top3_accuracy")}, indent=2))


if __name__ == "__main__":
    main()
