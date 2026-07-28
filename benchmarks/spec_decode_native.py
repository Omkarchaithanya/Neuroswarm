"""Pillar 1 — native llama.cpp speculative decoding benchmark (tier-spec)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.runtime.dipa.backends.llama_cpp import LlamaHttpClient

DEFAULT_SPEC_URL = os.getenv("NSA_TIER_SPEC_URL", "http://localhost:8084")
DEFAULT_BASELINE_URL = os.getenv("NSA_TIER2_URL", "http://localhost:8082")
DEFAULT_OUT = REPO_ROOT / "benchmarks" / "results" / "spec_decode_native.json"

PROMPTS = [
    "What is the capital of France?",
    "Summarize speculative decoding in one sentence.",
    "List three benefits of KleidiAI on Arm CPUs.",
]


def _chat(client: LlamaHttpClient, prompt: str, *, max_tokens: int = 64) -> dict[str, Any]:
    payload = client.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1,
        stream=False,
    )
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    completion = int((usage or {}).get("completion_tokens") or 0)
    text = ""
    if isinstance(payload, dict):
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            text = str(msg.get("content") or "")
    return {"completion_tokens": completion, "text": text, "raw": payload}


def _bench_url(url: str, label: str) -> dict[str, Any]:
    client = LlamaHttpClient(base_url=url, timeout_s=180.0)
    latencies: list[float] = []
    tokens = 0
    for prompt in PROMPTS:
        t0 = time.perf_counter()
        row = _chat(client, prompt)
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)
        tokens += max(1, int(row["completion_tokens"] or len(row["text"].split())))
    total_s = sum(latencies) or 1e-9
    return {
        "label": label,
        "url": url,
        "prompts": len(PROMPTS),
        "completion_tokens": tokens,
        "total_seconds": round(total_s, 4),
        "tok_per_s": round(tokens / total_s, 3),
        "latency_ms_mean": round(1000.0 * (total_s / len(PROMPTS)), 2),
    }


def run(*, spec_url: str, baseline_url: str) -> dict[str, Any]:
    spec = _bench_url(spec_url, "tier-spec-draft-simple")
    baseline = _bench_url(baseline_url, "tier2-no-spec")
    speedup = (
        spec["tok_per_s"] / baseline["tok_per_s"]
        if baseline["tok_per_s"] > 0
        else 0.0
    )
    return {
        "status": "ok",
        "spec": spec,
        "baseline": baseline,
        "measured_speedup": round(speedup, 3),
        "note": "Compare tier-spec (in-process draft-simple) vs standalone target server.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Native spec-decode benchmark")
    parser.add_argument("--spec-url", default=DEFAULT_SPEC_URL)
    parser.add_argument("--baseline-url", default=DEFAULT_BASELINE_URL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    try:
        payload = run(spec_url=args.spec_url, baseline_url=args.baseline_url)
    except Exception as exc:  # noqa: BLE001
        payload = {"status": "error", "error": str(exc)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
