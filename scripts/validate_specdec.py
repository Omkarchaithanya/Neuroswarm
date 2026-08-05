"""Validate speculative decoding pipeline.

This script performs a quick end‑to‑end validation of the speculative decoding
subsystem (draft model → DIPA → metrics). It runs a few prompts with
``speculative=True`` and compares them against a non‑speculative (baseline)
run.

The script:
1. Checks that the draft model service is reachable (via ``NSA_TIER_SPEC_URL``).
2. Executes a list of prompts through DIPA with speculative decoding enabled.
3. Collects ``ASR_METRICS`` counters defined in the llama_cpp backend.
4. Runs the same prompts with speculative disabled to obtain a baseline latency.
5. Prints a markdown table with the key metrics and writes a JSON report to
   ``work/validate_specdec.json``.
6. Exits with ``0`` when the acceptance rate is >10% *and* the speed‑up is >1.0x,
   otherwise exits with ``1``.

Usage:
    python scripts/validate_specdec.py
"""

import json
import os
import sys
import time
from typing import List

import requests

# DIPA imports – these are part of the repository
from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import ASR_METRICS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Prompts to exercise the pipeline – keep them short for a fast validation.
PROMPTS: List[str] = [
    "Write a haiku about sunrise.",
    "Explain quantum entanglement in two sentences.",
    "Summarize the plot of the movie Inception.",
]

# Environment variable pointing to the draft model server (set by docker‑compose).
SPEC_URL = os.getenv("NSA_TIER_SPEC_URL", "http://localhost:8081")

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def check_draft_service(url: str) -> bool:
    """Return ``True`` if the draft model health endpoint replies with 200.

    The llama‑cpp server exposes ``/health`` which returns ``{"status":"ok"}``.
    """
    try:
        resp = requests.get(f"{url}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def run_dipa(prompts: List[str], speculative: bool) -> dict:
    """Run a sequence of prompts through DIPA.

    Returns a dict with:
        * ``total_time`` – wall‑clock seconds for the whole batch.
        * ``metrics`` – a snapshot of ``ASR_METRICS`` after the run.
    """
    # Build a DIPA runtime – using a mock control plane for speed.
    dipa = build_dipa(use_mock=True, start=True)

    start = time.time()
    for txt in prompts:
        req = InferenceRequest(
            prompt_text=txt,
            max_tokens=256,
            temperature=0.7,
            speculative=speculative,
        )
        # The DIPA runtime manager exposes ``query`` for inference.
        dipa.query(txt, speculative=speculative)
    total_time = time.time() - start
    metrics_snapshot = ASR_METRICS.snapshot()
    return {"total_time": total_time, "metrics": metrics_snapshot}


def compute_acceptance_rate(metrics: dict) -> float:
    drafted = metrics.get("asr_draft_tokens_total", 0.0)
    accepted = metrics.get("asr_accepted_tokens_total", 0.0)
    if drafted == 0:
        return 0.0
    return accepted / drafted


def main() -> int:
    # 1. Verify draft service
    if not check_draft_service(SPEC_URL):
        print(f"[ERROR] Draft model service not reachable at {SPEC_URL}")
        return 1

    # 2. Run speculative and baseline passes
    spec_result = run_dipa(PROMPTS, speculative=True)
    base_result = run_dipa(PROMPTS, speculative=False)

    # 3. Extract metrics
    spec_metrics = spec_result["metrics"]
    draft_tokens = spec_metrics.get("asr_draft_tokens_total", 0.0)
    accepted_tokens = spec_metrics.get("asr_accepted_tokens_total", 0.0)
    acceptance_rate = compute_acceptance_rate(spec_metrics)
    tok_per_s = spec_metrics.get("asr_tok_per_s", 0.0)

    # 4. Compute speed‑up
    baseline_time = base_result["total_time"]
    speculative_time = spec_result["total_time"]
    speedup = baseline_time / speculative_time if speculative_time > 0 else 0.0
    time_saved_ms = (baseline_time - speculative_time) * 1000.0

    # 5. Print markdown table
    md_table = (
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| Draft Tokens | {draft_tokens:.0f} |\n"
        f"| Accepted Tokens | {accepted_tokens:.0f} |\n"
        f"| Acceptance Rate | {acceptance_rate:.2%} |\n"
        f"| Avg Tok/s | {tok_per_s:.2f} |\n"
        f"| Time Saved vs Baseline | {time_saved_ms:.0f} ms |\n"
        f"| Speed‑up | {speedup:.2f}x |\n"
    )
    print(md_table)

    # 6. Write JSON artifact
    report = {
        "draft_tokens": draft_tokens,
        "accepted_tokens": accepted_tokens,
        "acceptance_rate": acceptance_rate,
        "avg_tok_per_s": tok_per_s,
        "baseline_time_s": baseline_time,
        "speculative_time_s": speculative_time,
        "time_saved_ms": time_saved_ms,
        "speedup": speedup,
        "metrics_snapshot": spec_metrics,
    }
    os.makedirs("work", exist_ok=True)
    with open("work/validate_specdec.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # 7. Exit condition
    if acceptance_rate > 0.10 and speedup > 1.0:
        print("[PASS] Speculative decoding meets acceptance and speed‑up thresholds.")
        return 0
    else:
        print("[FAIL] Speculative decoding did not meet thresholds.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
