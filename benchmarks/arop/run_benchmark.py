"""AROP offline benchmark harness."""

from __future__ import annotations

import json
import time
from pathlib import Path

from neuroswarm_arm.evolution import build_arop, load_arop_config


def run_arop_benchmark(work_dir: Path | None = None, *, iterations: int = 5) -> dict:
    root = work_dir or Path("work/benchmarks/arop")
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_arop_config(work_dir=root / "runtime", okf_root=root / "okf")
    cfg.performix_enabled = False
    cfg.auto_promote = False
    cfg.min_improvement = 0.0
    cfg.significance_alpha = 1.0
    (root / "okf").mkdir(parents=True, exist_ok=True)

    runtime = build_arop(cfg)
    results = []
    t0 = time.perf_counter()
    for i in range(iterations):
        runtime.runtime_provider.record(
            {
                "ascr_accept_rate": 0.45 + i * 0.02,
                "ascr_latency_ms": 3200 - i * 100,
                "kv_pressure": 0.7,
                "cpu_util": 0.6,
                "draft_len": 8,
                "reward_scalar": 0.2 + i * 0.05,
            }
        )
        result = runtime.run_once()
        results.append(
            {
                "i": i,
                "status": result.status,
                "policy_id": result.policy_id,
                "message": result.message,
                "metrics": result.metrics,
            }
        )
    elapsed = time.perf_counter() - t0
    report = {
        "iterations": iterations,
        "elapsed_s": elapsed,
        "results": results,
        "registry": runtime.registry.status(),
        "health": runtime.health(),
    }
    out = root / "arop_benchmark.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_arop_benchmark(), indent=2))
