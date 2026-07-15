#!/usr/bin/env python3
"""KV restore benchmark."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuroswarm_arm.runtime.kv.benchmark import run_named_benchmark, write_report
from neuroswarm_arm.runtime.kv.factory import build_kv_runtime
from neuroswarm_arm.runtime.kv.utils.config import load_kv_config


async def main() -> None:
    cfg = load_kv_config(ROOT / "work" / "kv-bench")
    runtime = build_kv_runtime(cfg, enable_background=False)
    try:
        result = await run_named_benchmark(runtime, "restore", iterations=10)
        write_report(ROOT / "work" / "benchmarks" / "kv_restore.json", [result])
        print(result)
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
