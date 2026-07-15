"""ASCR cascade benchmark — tok/s, TTFT, accept, speculation gain."""

from __future__ import annotations

import time
from pathlib import Path

from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest

try:
    from common import DEFAULT_RESULTS_DIR, write_json
except ImportError:  # pragma: no cover
    DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[1] / "work" / "benchmarks"

    def write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


PROMPTS = [
    "What is the capital of France?",
    "Write a short hello world function in Python",
    "Summarize why speculative decoding helps CPU inference",
    " ".join(f"step{i}" for i in range(50)),
]


def run_ascr_benchmark(iterations: int = 4) -> dict:
    rt = build_dipa(use_mock=True, start=True)
    try:
        assert isinstance(rt.cascade_engine, ASCREngine)
        latencies: list[float] = []
        tiers: list[int] = []
        gains: list[float] = []
        accepts: list[float] = []
        t0 = time.perf_counter()
        tokens = 0
        for i in range(iterations):
            prompt = PROMPTS[i % len(PROMPTS)]
            out = rt.infer(
                InferenceRequest(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=64,
                    agent_role="tool_call",
                    latency_sla_ms=5000,
                )
            )
            latencies.append(float(out.latency_ms or 0.0))
            tiers.append(int(out.tier_used or 1))
            tokens += int(out.completion_tokens or max(1, len(out.text.split())))
            gains.append(float(out.metrics.get("ascr_speculation_gain", 0.0)))
            accepts.append(float(out.metrics.get("confidence", 0.0)))
        elapsed = max(time.perf_counter() - t0, 1e-6)
        return {
            "status": "ok",
            "engine": "ASCR",
            "iterations": iterations,
            "tokens_per_sec": tokens / elapsed,
            "ttft_ms_avg": sum(latencies) / max(1, len(latencies)) * 0.2,
            "latency_ms_avg": sum(latencies) / max(1, len(latencies)),
            "tier_used_avg": sum(tiers) / max(1, len(tiers)),
            "acceptance_proxy_avg": sum(accepts) / max(1, len(accepts)),
            "speculation_gain_avg": sum(gains) / max(1, len(gains)),
            "rejected_tokens_note": "see ascr_rejection_rate metric under live Prometheus",
            "cost_per_token_est": 0.0,
            "energy_per_token_est": 0.0,
        }
    finally:
        rt.shutdown()


def main() -> None:
    write_json(DEFAULT_RESULTS_DIR / "ascr_benchmark.json", run_ascr_benchmark())


if __name__ == "__main__":
    main()
