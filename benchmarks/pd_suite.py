"""PD benchmark suite — TTFT / prefix / recompute metrics (mock or live)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.runtime.dipa.factory import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.runtime.runtime_config import DIPARuntimeConfig


def run_once(rt, prompt: str, max_tokens: int = 32) -> dict:
    req = InferenceRequest(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    t0 = time.perf_counter()
    resp = rt.infer(req)
    elapsed = (time.perf_counter() - t0) * 1000.0
    return {
        "latency_ms": elapsed,
        "ttft_ms": float(resp.metrics.get("ttft_ms", elapsed)),
        "pd_enabled": float(resp.metrics.get("pd_enabled", 0.0)),
        "kv_transfer_mode": resp.metrics.get("kv_transfer_mode"),
        "recompute_tokens": float(resp.metrics.get("recompute_tokens", 0.0)),
        "prefix_hit_tokens": float(resp.metrics.get("prefix_hit_tokens", 0.0)),
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "backend": resp.backend,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DIPA PD benchmark suite")
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--pd-mode", default="soft", choices=["off", "soft", "native"])
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/results/pd_suite.json"))
    args = parser.parse_args()

    cfg = DIPARuntimeConfig(
        pd_mode=args.pd_mode,
        pd_min_prompt_tokens=1,
        chunk_size=64,
    )
    rt = build_dipa(cfg=cfg, use_mock=True, start=True)
    prompt = " ".join(f"word{i}" for i in range(200))
    rows = []
    try:
        for _ in range(args.iterations):
            rows.append(run_once(rt, prompt))
    finally:
        rt.shutdown()

    summary = {
        "pd_mode": args.pd_mode,
        "iterations": args.iterations,
        "avg_latency_ms": sum(r["latency_ms"] for r in rows) / max(1, len(rows)),
        "avg_ttft_ms": sum(r["ttft_ms"] for r in rows) / max(1, len(rows)),
        "avg_recompute_tokens": sum(r["recompute_tokens"] for r in rows)
        / max(1, len(rows)),
        "rows": rows,
        "metrics": {},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
