"""ACR benchmark harness — measurable compression, no fixed % target."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from neuroswarm_arm.runtime.acr import build_acr
from neuroswarm_arm.runtime.acr.config import ACRConfig


class _BenchMemory:
    def __init__(self) -> None:
        self.facts = [
            "User prefers Arm Neoverse CPUs for inference",
            "Cascade tier1 on NUMA0 tier2 on NUMA1",
            "Keep context small under token budget",
            "OKF policies override ad-hoc prompts",
            "Duplicate: User prefers Arm Neoverse CPUs for inference",
        ] * 5

    def recall(self, owner, query, *, limit=5, namespace=None):
        return self.facts[:limit]

    def remember_evolution(self, *a, **k):
        return None


class _BenchOKF:
    def query(self, text, agent_profile="architect"):
        body = (
            "Institutional knowledge: NEXUS uses HAOE, DIPA, ACR, MAKS. "
            "Progressive disclosure loads only needed OKF sections. " * 20
        )

        class R:
            tokens_used = 200
            sections = []
            text = body

        return R()

    def load_tool_docs(self, names, budget=600):
        class R:
            text = ("Tool documentation for " + ",".join(names) + ". ") * 30

        return R()


def run_bench(budget: int = 1000, repeat: int = 20) -> dict:
    acr = build_acr(
        memory=_BenchMemory(),
        okf=_BenchOKF(),
        config=ACRConfig(enabled=True, token_budget=budget, cache_enabled=True),
    )
    query = "Explain NUMA-aware cascade and cost policy for Arm coding agent with github tools"
    ratios = []
    retains = []
    latencies = []
    t0 = time.perf_counter()
    for i in range(repeat):
        snap = acr.build_context(
            query if i else query,
            owner="bench",
            agent_role="coding",
            tool_names=["github-mcp"],
            use_cache=(i > 0),
        )
        ratios.append(snap.stats.compression.compression_ratio)
        retains.append(snap.stats.compression.information_retained)
        latencies.append(snap.stats.total_latency_ms)
    elapsed = time.perf_counter() - t0
    result = {
        "repeat": repeat,
        "budget": budget,
        "avg_compression_ratio": sum(ratios) / len(ratios),
        "avg_token_reduction": 1.0 - (sum(ratios) / len(ratios)),
        "avg_information_retained": sum(retains) / len(retains),
        "avg_latency_ms": sum(latencies) / len(latencies),
        "p50_latency_ms": sorted(latencies)[len(latencies) // 2],
        "throughput_rps": repeat / elapsed if elapsed else 0.0,
        "cache_hit_ratio": acr.cache.hit_ratio(),
        "health": acr.health(),
        "note": "No fixed percentage target — maximize measured compression while retaining task info.",
    }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=1000)
    ap.add_argument("--repeat", type=int, default=20)
    ap.add_argument("--out", type=str, default="benchmarks/results/acr_bench.json")
    args = ap.parse_args()
    result = run_bench(budget=args.budget, repeat=args.repeat)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
