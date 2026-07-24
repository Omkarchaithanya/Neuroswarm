"""Pillar 4 — live ReasoningGovernor token-cap validation (real tier3)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.config import get_config
from neuroswarm_arm.governor import ReasoningGovernor
from neuroswarm_arm.runtime.dipa.backends.llama_cpp import LlamaHttpClient
from neuroswarm_arm.runtime.rtg import build_rtg
from neuroswarm_arm.schemas import PlanState

from benchmarks.cascade_acceptance_live import load_prompts
from benchmarks.common import write_json

DEFAULT_PROMPTS_PATH = REPO_ROOT / "benchmarks" / "test-data" / "governor_prompts.jsonl"
DEFAULT_RESULTS_PATH = REPO_ROOT / "benchmarks" / "results" / "governor_live.json"
DEFAULT_TIER3_URL = "http://localhost:8083"

LOG = logging.getLogger("governor_live")

# Loose PlanState → large governor cap (uncapped-equivalent baseline).
PLAN_LOOSE = PlanState(
    tool_confidence_top1=0.3,
    slo_remaining_ms=30000.0,
)

# Tight constraints → small governor cap.
PLAN_TIGHT = PlanState(
    tool_confidence_top1=0.88,
    kv_pressure=0.75,
    slo_remaining_ms=3000.0,
    self_consistency_score=0.9,
)


def _build_governor() -> ReasoningGovernor:
    """Wire RTG behind ReasoningGovernor; swallow Performix/MCP crashes."""
    rtg = None
    try:
        rtg = build_rtg()
    except Exception as exc:  # noqa: BLE001 — Pillar 1 Performix/MCP known crash
        warnings.warn(f"build_rtg failed (Performix/MCP?): {exc}", stacklevel=2)
        LOG.warning("build_rtg failed; falling back to legacy governor: %s", exc)
    try:
        return ReasoningGovernor(rtg=rtg)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(f"ReasoningGovernor init failed: {exc}", stacklevel=2)
        LOG.warning("ReasoningGovernor(rtg=...) failed; using legacy: %s", exc)
        return ReasoningGovernor()


def _prompt_text(row: dict[str, Any]) -> str:
    text = row.get("prompt")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"prompt row missing string 'prompt': {row!r}")
    return text


def _completion_tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0
    return int(usage.get("completion_tokens") or 0)


def _chat_once(
    client: LlamaHttpClient,
    *,
    prompt: str,
    max_tokens: int,
) -> tuple[int, float]:
    t0 = time.perf_counter()
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return _completion_tokens(resp), elapsed_ms


def run_live_governor(
    *,
    prompts_path: Path = DEFAULT_PROMPTS_PATH,
    results_path: Path = DEFAULT_RESULTS_PATH,
    tier3_url: str | None = None,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app_cfg = get_config()
    url = (tier3_url or os.getenv("NSA_TIER3_URL") or DEFAULT_TIER3_URL).rstrip("/")
    prompts = load_prompts(prompts_path)

    governor = _build_governor()
    try:
        cap_a = int(governor.cap(PLAN_LOOSE))
        cap_b = int(governor.cap(PLAN_TIGHT))
    except Exception as exc:  # noqa: BLE001 — sensor/Performix path during cap
        warnings.warn(f"governor.cap failed: {exc}", stacklevel=2)
        LOG.warning("governor.cap failed; retrying legacy: %s", exc)
        governor = ReasoningGovernor()
        cap_a = int(governor.cap(PLAN_LOOSE))
        cap_b = int(governor.cap(PLAN_TIGHT))

    client = LlamaHttpClient(base_url=url, timeout_s=180.0)
    per_prompt: list[dict[str, Any]] = []
    tokens_a: list[int] = []
    tokens_b: list[int] = []
    latency_a: list[float] = []
    latency_b: list[float] = []

    for idx, row in enumerate(prompts):
        prompt = _prompt_text(row)
        pid = str(row.get("id") or row.get("type") or f"prompt_{idx}")
        tok_a, ms_a = _chat_once(client, prompt=prompt, max_tokens=cap_a)
        tok_b, ms_b = _chat_once(client, prompt=prompt, max_tokens=cap_b)
        tokens_a.append(tok_a)
        tokens_b.append(tok_b)
        latency_a.append(ms_a)
        latency_b.append(ms_b)
        per_prompt.append(
            {
                "id": pid,
                "type": row.get("type"),
                "completion_tokens_a": tok_a,
                "completion_tokens_b": tok_b,
                "latency_a_ms": round(ms_a, 2),
                "latency_b_ms": round(ms_b, 2),
                "cap_a": cap_a,
                "cap_b": cap_b,
            }
        )
        LOG.info(
            "%s tokens_a=%d tokens_b=%d latency_a_ms=%.1f latency_b_ms=%.1f",
            pid,
            tok_a,
            tok_b,
            ms_a,
            ms_b,
        )

    n = len(per_prompt) or 1
    avg_a = sum(tokens_a) / n
    avg_b = sum(tokens_b) / n
    pct_reduction = ((avg_a - avg_b) / avg_a * 100.0) if avg_a > 0 else 0.0
    payload: dict[str, Any] = {
        "status": "ok",
        "pillar": "pillar_4_governor_live",
        "sample_size": len(per_prompt),
        "avg_tokens_run_a": round(avg_a, 3),
        "avg_tokens_run_b": round(avg_b, 3),
        "pct_reduction": round(pct_reduction, 3),
        "avg_latency_a_ms": round(sum(latency_a) / n, 3),
        "avg_latency_b_ms": round(sum(latency_b) / n, 3),
        "cap_a_used": cap_a,
        "cap_b_used": cap_b,
        "plan_a": PLAN_LOOSE.model_dump(),
        "plan_b": PLAN_TIGHT.model_dump(),
        "config": {
            "tier3_url": url,
            "temperature": 0.0,
            "model_tier3": app_cfg.model_tier3,
            "prompts_path": str(prompts_path),
        },
        "per_prompt": per_prompt,
    }
    write_json(results_path, payload)

    print("=== governor_live summary ===")
    print(f"sample_size={payload['sample_size']}")
    print(f"cap_a_used={cap_a}  cap_b_used={cap_b}")
    print(f"avg_tokens_run_a={payload['avg_tokens_run_a']}")
    print(f"avg_tokens_run_b={payload['avg_tokens_run_b']}")
    print(f"pct_reduction={payload['pct_reduction']}")
    print(f"avg_latency_a_ms={payload['avg_latency_a_ms']}")
    print(f"avg_latency_b_ms={payload['avg_latency_b_ms']}")
    print("--- per-prompt tokens ---")
    for row in per_prompt:
        print(
            f"{row['id']}: a={row['completion_tokens_a']} b={row['completion_tokens_b']}"
        )
    print(f"wrote {results_path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live ReasoningGovernor tier3 token-savings benchmark"
    )
    parser.add_argument(
        "--prompts",
        default=str(DEFAULT_PROMPTS_PATH),
        help="JSONL prompt suite (default: benchmarks/test-data/governor_prompts.jsonl)",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RESULTS_PATH),
        help="Output JSON path (default: benchmarks/results/governor_live.json)",
    )
    parser.add_argument(
        "--tier3-url",
        default=None,
        help=f"tier3 llama-server URL (env NSA_TIER3_URL, default {DEFAULT_TIER3_URL})",
    )
    args = parser.parse_args()
    run_live_governor(
        prompts_path=Path(args.prompts),
        results_path=Path(args.out),
        tier3_url=args.tier3_url,
    )


if __name__ == "__main__":
    main()
