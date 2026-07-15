"""CLI entry: python -m neuroswarm_arm.runtime.router.benchmarks.runner"""

from __future__ import annotations

from pathlib import Path
import argparse
import json

from neuroswarm_arm.runtime.router import build_router, load_router_config
from neuroswarm_arm.runtime.router.benchmarks.runner import run_router_benchmark, write_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic MCP Tool Router benchmarks")
    parser.add_argument("--out", type=Path, default=Path("work/benchmarks/router_accuracy.json"))
    parser.add_argument("--backend", default="exact")
    args = parser.parse_args()
    cfg = load_router_config()
    cfg.enable_hot_reload = False
    cfg.ann_backend = args.backend
    router = build_router(cfg, start_sync=False)
    result = run_router_benchmark(router)
    write_benchmark(result, args.out)
    print(json.dumps({"wrote": str(args.out), "top3": result["top3_accuracy"]}, indent=2))


if __name__ == "__main__":
    main()
