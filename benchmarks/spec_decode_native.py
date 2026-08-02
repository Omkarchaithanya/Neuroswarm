"""Pillar 1 — native llama.cpp speculative decoding benchmark (tier-spec)."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ImportError:  # pragma: no cover - CI/host without tenacity
    def retry(*_a, **_k):  # type: ignore[misc]
        def _wrap(fn):
            return fn

        return _wrap

    def stop_after_attempt(*_a, **_k):  # type: ignore[misc]
        return None

    def wait_exponential(*_a, **_k):  # type: ignore[misc]
        return None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.runtime.dipa.backends.llama_cpp import LlamaHttpClient

DEFAULT_BASELINE_URL = os.getenv("NSA_TIER2_URL", "http://localhost:8082")
DEFAULT_OUT = REPO_ROOT / "benchmarks" / "results" / "spec_decode_native.json"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "spec_decode"

PROMPTS = [
    "What is the capital of France?",
    "Summarize speculative decoding in one sentence.",
    "List three benefits of KleidiAI on Arm CPUs.",
]


def _probe_url(url: str, *, timeout_s: float = 2.0) -> bool:
    from urllib import error, request

    try:
        with request.urlopen(url.rstrip("/") + "/health", timeout=timeout_s) as resp:
            return 200 <= int(getattr(resp, "status", 200) or 200) < 500
    except Exception:
        try:
            with request.urlopen(url.rstrip("/") + "/v1/models", timeout=timeout_s) as resp:
                return 200 <= int(getattr(resp, "status", 200) or 200) < 500
        except (error.URLError, TimeoutError, OSError, ValueError):
            return False


def resolve_spec_url(explicit: str | None = None) -> str:
    """Env → compose DNS → host port; empty env self-heals."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env = os.getenv("NSA_TIER_SPEC_URL", "").strip()
    if env:
        return env
    for candidate in ("http://tier-spec:8080", "http://localhost:8084"):
        if _probe_url(candidate):
            return candidate
    return "http://localhost:8084"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4), reraise=True)
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


def _bench_url(url: str, label: str, *, rounds: int = 1) -> dict[str, Any]:
    client = LlamaHttpClient(base_url=url, timeout_s=180.0)
    round_tps: list[float] = []
    all_latencies: list[float] = []
    total_tokens = 0
    total_s = 0.0
    for _ in range(max(1, rounds)):
        latencies: list[float] = []
        tokens = 0
        for prompt in PROMPTS:
            t0 = time.perf_counter()
            row = _chat(client, prompt)
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed)
            tokens += max(1, int(row["completion_tokens"] or len(row["text"].split())))
        round_s = sum(latencies) or 1e-9
        round_tps.append(tokens / round_s)
        all_latencies.extend(latencies)
        total_tokens += tokens
        total_s += round_s
    median_tps = statistics.median(round_tps) if round_tps else 0.0
    return {
        "label": label,
        "url": url,
        "prompts": len(PROMPTS),
        "rounds": max(1, rounds),
        "completion_tokens": total_tokens,
        "total_seconds": round(total_s, 4),
        "tok_per_s": round(median_tps, 3),
        "tok_per_s_rounds": [round(x, 3) for x in round_tps],
        "latency_ms_mean": round(
            1000.0 * (sum(all_latencies) / max(1, len(all_latencies))), 2
        ),
    }


def run(*, spec_url: str, baseline_url: str, rounds: int = 3) -> dict[str, Any]:
    spec = _bench_url(spec_url, "tier-spec-draft-simple", rounds=rounds)
    baseline = _bench_url(baseline_url, "tier2-no-spec", rounds=rounds)
    speedup = (
        spec["tok_per_s"] / baseline["tok_per_s"]
        if baseline["tok_per_s"] > 0
        else 0.0
    )
    note = "Compare tier-spec (in-process draft-simple) vs standalone target server."
    if speedup < 1.3:
        note += (
            " measured_speedup < 1.3× — draft and target may share the same GGUF;"
            " a real smaller draft GGUF would push speedup higher."
        )
    return {
        "status": "ok",
        "spec": spec,
        "baseline": baseline,
        "measured_speedup": round(speedup, 3),
        "note": note,
    }


def _markdown_table(payload: dict[str, Any]) -> str:
    spec = payload.get("spec") or {}
    baseline = payload.get("baseline") or {}
    lines = [
        "| arm | url | tok/s (median) | latency_ms_mean | completion_tokens |",
        "|---|---|---:|---:|---:|",
        (
            f"| {spec.get('label', 'spec')} | `{spec.get('url', '')}` | "
            f"{spec.get('tok_per_s', 0)} | {spec.get('latency_ms_mean', 0)} | "
            f"{spec.get('completion_tokens', 0)} |"
        ),
        (
            f"| {baseline.get('label', 'baseline')} | `{baseline.get('url', '')}` | "
            f"{baseline.get('tok_per_s', 0)} | {baseline.get('latency_ms_mean', 0)} | "
            f"{baseline.get('completion_tokens', 0)} |"
        ),
        "",
        f"**measured_speedup:** {payload.get('measured_speedup', 0)}×",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Native spec-decode benchmark")
    parser.add_argument("--spec-url", default=None, help="Override NSA_TIER_SPEC_URL")
    parser.add_argument("--baseline-url", default=DEFAULT_BASELINE_URL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--rounds", type=int, default=3, help="Repeat prompt set N times; report median tok/s")
    args = parser.parse_args()
    spec_url = resolve_spec_url(args.spec_url)
    try:
        payload = run(
            spec_url=spec_url,
            baseline_url=args.baseline_url,
            rounds=max(1, int(args.rounds)),
        )
    except Exception as exc:  # noqa: BLE001
        payload = {"status": "error", "error": str(exc)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = EVIDENCE_DIR / f"run_{stamp}.json"
    evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if payload.get("status") == "ok":
        print(_markdown_table(payload))
        print()
    print(json.dumps(payload, indent=2))
    print(f"wrote {evidence_path}", file=sys.stderr)
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
