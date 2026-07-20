#!/usr/bin/env python3
"""Axion demo benchmark suite — phased comparison table."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.common import system_snapshot, write_json
from benchmarks.slot_reuse import run_benchmark as run_slot_reuse


def _run_script(script: str, *args: str) -> dict:
    cmd = [sys.executable, str(ROOT / script), *args]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        return json.loads(out)
    except Exception as exc:
        return {"status": "error", "error": str(exc), "script": script}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "work" / "benchmarks" / "axion_demo_suite.json",
    )
    parser.add_argument("--sessions", type=int, default=5)
    parser.add_argument("--turns", type=int, default=10)
    args = parser.parse_args()

    baseline = run_slot_reuse(
        base_url=args.url,
        sessions=args.sessions,
        turns=args.turns,
        max_tokens=24,
    )
    kleidiai = _run_script(
        "scripts/validate_kleidiai.py",
        "--url",
        args.url,
        "--out",
        str(ROOT / "work" / "benchmarks" / "kleidiai_validation.json"),
    )

    report = {
        "status": "ok",
        "host": system_snapshot(),
        "phases": {
            "baseline_slot_reuse": baseline,
            "kleidiai_validation": kleidiai,
        },
        "summary_table": [
            {
                "phase": "baseline",
                "ttft_p50_turn1_ms": baseline.get("turn1_latency_ms_p50"),
                "ttft_p50_turn2plus_ms": baseline.get("turn2plus_latency_ms_p50"),
                "ttft_improvement_ratio": baseline.get("ttft_improvement_ratio"),
                "cached_tokens_mean": baseline.get("cached_tokens_mean"),
                "kleidiai_ok": kleidiai.get("ok"),
            },
        ],
    }
    write_json(args.out, report)

    md_path = args.out.with_suffix(".md")
    lines = [
        "# Axion Demo Benchmark Summary",
        "",
        "| Phase | TTFT p50 T1 | TTFT p50 T2+ | Improvement | Cached tokens | KleidiAI |",
        "|-------|-------------|--------------|-------------|---------------|----------|",
    ]
    for row in report["summary_table"]:
        lines.append(
            f"| {row['phase']} | {row['ttft_p50_turn1_ms']} | "
            f"{row['ttft_p50_turn2plus_ms']} | {row['ttft_improvement_ratio']} | "
            f"{row['cached_tokens_mean']} | {row['kleidiai_ok']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {args.out} and {md_path}")


if __name__ == "__main__":
    main()
