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


def _radix_prefix_probe() -> dict:
    from neuroswarm_arm.runtime.radix_slot_router import RadixSlotRouter
    from neuroswarm_arm.runtime.slot_registry import SlotRegistry

    router = RadixSlotRouter(registry=SlotRegistry(total_slots=4), min_match=64)
    prefix = list(range(200))
    router.insert(prefix, id_slot=0)
    slot, matched = router.match_longest_prefix(prefix + [999])
    snap = router.metrics.snapshot()
    return {
        "matched_slot": slot,
        "matched_len": matched,
        "radix_prefix_hit_total": snap["radix_prefix_hit_total"],
    }


def _performix_probe() -> dict:
    if os.getenv("NSA_PERFORMIX_SAMPLE", "0") != "1":
        return {"available": False, "performix_skipped": True, "reason": "NSA_PERFORMIX_SAMPLE!=1"}
    try:
        from neuroswarm_arm.telemetry.performix_bridge import PerformixBridge

        bridge = PerformixBridge(mcp_url=os.getenv("NSA_AROP_PERFORMIX_MCP", ""))
        return {
            "available": bridge.available,
            "tools": bridge._tools,
            "performix_skipped": not bridge.available,
        }
    except Exception as exc:
        return {"available": False, "performix_skipped": True, "error": str(exc)}


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
    q8_bench = _run_script("benchmarks/q8_codec_bench.py")
    radix = _radix_prefix_probe()
    performix = _performix_probe()

    ttft_ratio = baseline.get("ttft_improvement_ratio") or 0.0
    q8_ratio = (q8_bench.get("q8_bench") or {}).get("f32_compression_ratio")
    if q8_ratio is None:
        q8_ratio = (q8_bench.get("q8_bench") or {}).get("compression_ratio")
    milestones = {
        "pillar1_kleidiai_active": bool(kleidiai.get("ok")),
        "pillar1_speedup_target": "1.8-2.3x",
        "pillar1_speedup_observed": ttft_ratio,
        "pillar3_prefix_reuse_proxy": radix.get("radix_prefix_hit_total", 0) > 0,
        "layer5_maks_q8_ratio_target": 0.27,
        "layer5_maks_q8_ratio_observed": q8_ratio,
        "week1_performix_validated": performix.get("available", False),
    }

    report = {
        "status": "ok",
        "host": system_snapshot(),
        "phases": {
            "baseline_slot_reuse": baseline,
            "kleidiai_validation": kleidiai,
            "q8_codec_bench": q8_bench,
            "radix_prefix_probe": radix,
            "performix_probe": performix,
        },
        "milestones": milestones,
        "summary_table": [
            {
                "phase": "baseline",
                "ttft_p50_turn1_ms": baseline.get("turn1_latency_ms_p50"),
                "ttft_p50_turn2plus_ms": baseline.get("turn2plus_latency_ms_p50"),
                "ttft_improvement_ratio": ttft_ratio,
                "cached_tokens_mean": baseline.get("cached_tokens_mean"),
                "kleidiai_ok": kleidiai.get("ok"),
                "kleidiai_median_tok_s": (kleidiai.get("benchmark") or {}).get("median_tok_s"),
                "radix_prefix_hit_total": radix.get("radix_prefix_hit_total"),
                "q8_compression_ratio": q8_ratio,
                "performix_available": performix.get("available"),
            },
        ],
    }
    write_json(args.out, report)

    md_path = args.out.with_suffix(".md")
    lines = [
        "# Axion Demo Benchmark Summary",
        "",
        "| Phase | TTFT p50 T1 | TTFT p50 T2+ | Improvement | Cached | KleidiAI | Radix hits | Q8 ratio | Performix |",
        "|-------|-------------|--------------|-------------|--------|----------|------------|----------|-----------|",
    ]
    for row in report["summary_table"]:
        lines.append(
            f"| {row['phase']} | {row['ttft_p50_turn1_ms']} | "
            f"{row['ttft_p50_turn2plus_ms']} | {row['ttft_improvement_ratio']} | "
            f"{row['cached_tokens_mean']} | {row['kleidiai_ok']} | "
            f"{row['radix_prefix_hit_total']} | {row['q8_compression_ratio']} | "
            f"{row['performix_available']} |"
        )
    lines.extend(
        [
            "",
            "## Milestones",
            "",
            f"- Pillar 1 KleidiAI active: {milestones['pillar1_kleidiai_active']}",
            f"- Pillar 1 speedup observed: {milestones['pillar1_speedup_observed']} (target {milestones['pillar1_speedup_target']})",
            f"- Pillar 3 prefix reuse proxy: {milestones['pillar3_prefix_reuse_proxy']}",
            f"- Layer 5 Q8 ratio: {milestones['layer5_maks_q8_ratio_observed']} (target <= {milestones['layer5_maks_q8_ratio_target']})",
            f"- Performix available: {milestones['week1_performix_validated']}",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {args.out} and {md_path}")


if __name__ == "__main__":
    main()
