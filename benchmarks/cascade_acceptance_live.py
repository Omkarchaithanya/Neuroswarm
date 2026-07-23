"""Pillar 1 — live cascade acceptance-rate validation (real tier1/tier2 models)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from neuroswarm_arm.config import get_config
from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config
from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.benchmark import BenchmarkRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS_PATH = REPO_ROOT / "benchmarks" / "test-data" / "agent_prompts.jsonl"
DEFAULT_RESULTS_PATH = REPO_ROOT / "benchmarks" / "results" / "acceptance_rate_live.json"


def load_prompts(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"missing prompt suite: {path}")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError(f"prompt row must be object: {line[:80]}")
        rows.append(row)
    if not rows:
        raise ValueError(f"no prompts in {path}")
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _ascr_snapshot(runtime: Any) -> dict[str, float]:
    engine = getattr(runtime, "cascade_engine", None)
    metrics = getattr(engine, "metrics", None)
    snap = getattr(metrics, "snapshot", None)
    if callable(snap):
        return {k: float(v) for k, v in snap().items()}
    return {}


def run_live_acceptance(
    *,
    prompts_path: Path = DEFAULT_PROMPTS_PATH,
    results_path: Path = DEFAULT_RESULTS_PATH,
) -> dict[str, Any]:
    app_cfg = get_config()
    ascr_cfg = load_ascr_config()
    prompts = load_prompts(prompts_path)

    rt = build_dipa(
        use_mock=False,
        start=True,
        tier_urls={
            "tier1": app_cfg.tier1_url,
            "tier2": app_cfg.tier2_url,
            "tier3": app_cfg.tier3_url,
        },
    )
    try:
        result = BenchmarkRunner(rt).run(iterations=len(prompts), prompts=prompts)
        ascr_metrics = _ascr_snapshot(rt)
        payload: dict[str, Any] = {
            "status": "ok",
            "pillar": "pillar_1_live_acceptance",
            "overall_acceptance_rate": result.overall_acceptance_rate,
            "avg_speedup_vs_baseline": result.avg_speedup_vs_baseline,
            "sample_size": result.sample_size,
            "per_prompt_type": result.per_prompt_type,
            "avg_latency_ms": result.avg_latency_ms,
            "config": {
                "ascr_enabled": bool(ascr_cfg.get("enabled", True)),
                "draft_len": int((ascr_cfg.get("defaults") or {}).get("draft_len", 8)),
                "accept_threshold": float(
                    (ascr_cfg.get("defaults") or {}).get("accept_threshold", 0.7)
                ),
                "tier_urls": {
                    "tier1": app_cfg.tier1_url,
                    "tier2": app_cfg.tier2_url,
                    "tier3": app_cfg.tier3_url,
                },
                "model_paths": {
                    "tier1": app_cfg.model_tier1,
                    "tier2": app_cfg.model_tier2,
                    "tier3": app_cfg.model_tier3,
                },
            },
            "ascr_prometheus": {
                k: ascr_metrics[k]
                for k in (
                    "ascr_acceptance_rate",
                    "ascr_rejection_rate",
                    "ascr_speculation_gain",
                    "ascr_rounds_total",
                    "ascr_escalations_total",
                )
                if k in ascr_metrics
            },
            "per_request": [
                {
                    "prompt_type": r.prompt_type,
                    "tokens_proposed": r.tokens_proposed,
                    "tokens_accepted": r.tokens_accepted,
                    "tier_used": r.tier_used,
                    "latency_ms": r.latency_ms,
                    "speedup_vs_baseline": r.speedup_vs_baseline,
                }
                for r in result.per_request
            ],
        }
        write_json(results_path, payload)
        return payload
    finally:
        rt.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Live ASCR cascade acceptance benchmark")
    parser.add_argument(
        "--prompts",
        default=str(DEFAULT_PROMPTS_PATH),
        help="JSONL prompt suite (default: benchmarks/test-data/agent_prompts.jsonl)",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RESULTS_PATH),
        help="Output JSON path (default: benchmarks/results/acceptance_rate_live.json)",
    )
    args = parser.parse_args()
    run_live_acceptance(
        prompts_path=Path(args.prompts),
        results_path=Path(args.out),
    )


if __name__ == "__main__":
    main()
