#!/usr/bin/env python3
"""Render speculative tool-call evidence (summary.md + PNGs) from bench JSON.

matplotlib lives in pyproject dependency-group ``bench`` (not requirements-gateway.txt).
Install: ``uv sync --group bench`` (or ``--all-groups``).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "benchmarks" / "results" / "speculative_tool_bench.json"
DEFAULT_OUT = ROOT / "docs" / "evidence" / "speculative_tool"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_summary(data: dict, out_dir: Path) -> Path:
    summary = data.get("summary") or {}
    cfg = data.get("config") or {}
    system = data.get("system") or {}
    prompts = list(data.get("prompts") or [])
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    platform = system.get("platform") or system.get("machine") or "unknown"
    lines = [
        "# Speculative tool calling — evidence",
        "",
        f"status: captured  ",
        f"generated: {ts}  ",
        f"host: `{platform}`  ",
        f"mode: `{data.get('mode', 'inproc')}`  ",
        "",
        "Judges: read this in ~60 seconds.",
        "",
        "## Architecture",
        "",
        "```text",
        "  draft predictor ----+",
        "                      +--> SpeculativeExecutor --> ToolOutputCache / MCP",
        "  cascade generate ---+         |",
        "                                v",
        "                      match tool_call key -> speculative_hit + time_saved",
        "```",
        "",
        "- Baseline: `NSA_TOOL_SPEC_ENABLED=0` — cascade then sync MCP (no overlap).",
        "- Speculative: `NSA_TOOL_SPEC_ENABLED=1` — predict || cascade; warm half prompts first.",
        "- Prompts: `benchmarks/test-data/tool_prompts.jsonl` (10 calculator / 10 echo / 10 search).",
        "",
        "## Measured summary",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| hit_rate | **{summary.get('hit_rate', 0)}** |",
        f"| avg_time_saved_ms | **{summary.get('avg_time_saved_ms', 0)}** |",
        f"| p50 time_saved_ms | **{summary.get('p50', 0)}** |",
        f"| p95 time_saved_ms | **{summary.get('p95', 0)}** |",
        f"| tokens_per_dollar_delta | **{summary.get('tokens_per_dollar_delta', 0)}** |",
        f"| mean latency baseline_ms | {summary.get('mean_latency_baseline_ms', 0)} |",
        f"| mean latency speculative_ms | {summary.get('mean_latency_speculative_ms', 0)} |",
        f"| predicted_correct_rate | {summary.get('predicted_correct_rate', 0)} |",
        f"| latency_speedup | {summary.get('latency_speedup', 0)} |",
        "",
        f"Warm prompts: **{cfg.get('warm_n', 0)}** / {cfg.get('prompts', len(prompts))}.",
        "",
        "## Artifacts",
        "",
        "| file | what |",
        "|---|---|",
        "| `speculative_tool_bench.json` | full jq-able result + per-prompt rows |",
        "| `speculative_tool_bench.csv` | flat table for spreadsheets |",
        "| `hit_rate.png` | cache-hit vs miss counts |",
        "| `latency_cdf.png` | CDF of time_saved_ms |",
        "",
        "## Reproduce",
        "",
        "```bash",
        "make bench-tool-spec",
        "# or:",
        "uv run python benchmarks/speculative_tool_bench.py \\",
        "  --out benchmarks/results/speculative_tool_bench.json",
        "uv run --group bench python scripts/render_speculative_tool_evidence.py",
        "```",
        "",
        "## Honesty",
        "",
        "- Default mode is **inproc** (real `SpeculativeEngine` + timed FakeMCP).",
        "- Cascade/MCP delays configurable via `NSA_TOOL_SPEC_BENCH_CASCADE_S` / `_MCP_S`.",
        "- `tokens_per_dollar_delta` = ref_tpd * (baseline_ms/spec_ms - 1); ref from `NSA_TOOL_SPEC_REF_TPD` (default 12580).",
        "- Live gateway: add `--live` (needs stack up; slower than 5 min budget if LLM cold).",
        "",
    ]
    path = out_dir / "summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def plot_hit_rate(data: dict, out_path: Path) -> None:
    prompts = list(data.get("prompts") or [])
    hits = sum(1 for r in prompts if r.get("cache_hit"))
    misses = max(0, len(prompts) - hits)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    bars = ax.bar(["cache_hit", "cache_miss"], [hits, misses], color=["#264653", "#e76f51"])
    ax.set_ylabel("prompt count")
    ax.set_title("Speculative tool cache hit vs miss")
    summary = data.get("summary") or {}
    ax.text(
        0.98,
        0.95,
        f"hit_rate={summary.get('hit_rate', 0):.3f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
    )
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h, f" {int(h)}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_latency_cdf(data: dict, out_path: Path) -> None:
    prompts = list(data.get("prompts") or [])
    saved = sorted(float(r.get("time_saved_ms") or 0.0) for r in prompts)
    if not saved:
        saved = [0.0]
    ys = [(i + 1) / len(saved) for i in range(len(saved))]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(saved, ys, color="#2a9d8f", linewidth=2.2, drawstyle="steps-post")
    ax.set_xlabel("time_saved_ms")
    ax.set_ylabel("CDF")
    ax.set_title("Latency savings CDF (baseline − speculative)")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)
    summary = data.get("summary") or {}
    ax.axvline(float(summary.get("p50") or 0), color="#e9c46a", linestyle="--", label="p50")
    ax.axvline(float(summary.get("p95") or 0), color="#e76f51", linestyle="--", label="p95")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    data = _load(args.inp)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # Prefer copying companion CSV if adjacent to JSON.
    csv_src = args.inp.with_suffix(".csv")
    if csv_src.is_file():
        (out_dir / csv_src.name).write_bytes(csv_src.read_bytes())
    json_dst = out_dir / args.inp.name
    if args.inp.resolve() != json_dst.resolve():
        json_dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
    summary_path = write_summary(data, out_dir)
    hit_png = out_dir / "hit_rate.png"
    cdf_png = out_dir / "latency_cdf.png"
    plot_hit_rate(data, hit_png)
    plot_latency_cdf(data, cdf_png)
    print(
        json.dumps(
            {
                "summary_md": str(summary_path),
                "hit_rate_png": str(hit_png),
                "latency_cdf_png": str(cdf_png),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
