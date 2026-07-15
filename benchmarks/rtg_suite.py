"""RTG benchmark suite — No / Fixed / Dynamic(legacy) / Adaptive baselines."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.governor import ReasoningGovernor
from neuroswarm_arm.runtime.rtg import build_rtg
from neuroswarm_arm.runtime.rtg.models import TelemetryFrame
from neuroswarm_arm.schemas import PlanState

from common import DEFAULT_RESULTS_DIR, write_json


SCENARIOS = [
    {
        "name": "easy_tool",
        "prompt": "Send a slack message about the release",
        "tool_confidence_top1": 0.92,
        "kv_pressure": 0.15,
        "slo_remaining_ms": 8000.0,
        "self_consistency_score": 0.2,
        "complexity": 0.2,
    },
    {
        "name": "medium_kv_pressure",
        "prompt": "Explain cascade routing under memory pressure " * 8,
        "tool_confidence_top1": 0.55,
        "kv_pressure": 0.82,
        "slo_remaining_ms": 5000.0,
        "self_consistency_score": 0.25,
        "complexity": 0.55,
    },
    {
        "name": "hard_slo",
        "prompt": "Derive a multi-step proof for the routing optimality bound " * 6,
        "tool_confidence_top1": 0.35,
        "kv_pressure": 0.25,
        "slo_remaining_ms": 2200.0,
        "self_consistency_score": 0.15,
        "complexity": 0.85,
    },
    {
        "name": "high_consistency",
        "prompt": "Confirm the final answer is 42",
        "tool_confidence_top1": 0.7,
        "kv_pressure": 0.1,
        "slo_remaining_ms": 6000.0,
        "self_consistency_score": 0.94,
        "complexity": 0.3,
    },
]


def _plan(s: dict) -> PlanState:
    return PlanState(
        tool_confidence_top1=s["tool_confidence_top1"],
        kv_pressure=s["kv_pressure"],
        slo_remaining_ms=s["slo_remaining_ms"],
        self_consistency_score=s["self_consistency_score"],
    )


def _frame(s: dict) -> TelemetryFrame:
    return TelemetryFrame(
        session_id=s["name"],
        prompt_text=s["prompt"],
        tool_confidence_top1=s["tool_confidence_top1"],
        kv_pressure=s["kv_pressure"],
        slo_remaining_ms=s["slo_remaining_ms"],
        self_consistency_score=s["self_consistency_score"],
        complexity_score=s["complexity"],
    )


def baseline_none(s: dict) -> dict:
    return {"name": s["name"], "budget": 8192, "mode": "none"}


def baseline_fixed(s: dict, fixed: int = 2048) -> dict:
    return {"name": s["name"], "budget": fixed, "mode": "fixed"}


def baseline_dynamic_legacy(s: dict) -> dict:
    gov = ReasoningGovernor()  # no RTG → legacy
    cap = gov.cap(_plan(s))
    return {"name": s["name"], "budget": cap, "mode": "dynamic_legacy"}


def baseline_adaptive(rtg, s: dict) -> dict:
    t0 = time.perf_counter()
    state = rtg.admit(_frame(s))
    # Simulate 3 decode chunks
    text = "reasoning step. "
    last = None
    for i in range(3):
        last = rtg.on_chunk(
            state.session_id,
            text * (i + 1),
            tokens=32,
            latency_ms=15.0,
            self_consistency_score=s["self_consistency_score"] if i == 2 else 0.3,
            kv_pressure=s["kv_pressure"],
        )
        if last.terminal:
            break
    rtg.on_complete(state.session_id, text)
    elapsed = (time.perf_counter() - t0) * 1000.0
    used = state.budget.initial_tokens - state.budget.remaining_tokens
    return {
        "name": s["name"],
        "budget": state.budget.initial_tokens,
        "tokens_used_proxy": used,
        "last_action": last.action.value if last else "CONTINUE",
        "latency_ms": elapsed,
        "mode": "adaptive_rtg",
    }


def evaluate_rtg_suite() -> dict:
    rtg = build_rtg()
    rows = []
    for s in SCENARIOS:
        rows.append(
            {
                "scenario": s["name"],
                "none": baseline_none(s),
                "fixed": baseline_fixed(s),
                "dynamic_legacy": baseline_dynamic_legacy(s),
                "adaptive": baseline_adaptive(rtg, s),
            }
        )
    adaptive_budgets = [r["adaptive"]["budget"] for r in rows]
    legacy_budgets = [r["dynamic_legacy"]["budget"] for r in rows]
    reduction_vs_none = [
        1.0 - (a / 8192.0) for a in adaptive_budgets
    ]
    reduction_vs_legacy = [
        (l - a) / max(1, l) for a, l in zip(adaptive_budgets, legacy_budgets)
    ]
    return {
        "status": "ok",
        "scenarios": rows,
        "summary": {
            "adaptive_mean_budget": statistics.mean(adaptive_budgets),
            "legacy_mean_budget": statistics.mean(legacy_budgets),
            "mean_reduction_vs_none": statistics.mean(reduction_vs_none),
            "mean_reduction_vs_legacy": statistics.mean(reduction_vs_legacy),
            "p50_adaptive": statistics.median(adaptive_budgets),
        },
    }


def main() -> None:
    result = evaluate_rtg_suite()
    write_json(DEFAULT_RESULTS_DIR / "rtg_suite.json", result)
    # Keep legacy artifact name updated
    from common import evaluate_governor

    write_json(DEFAULT_RESULTS_DIR / "governor_tokens.json", evaluate_governor())
    print(result["summary"])


if __name__ == "__main__":
    main()
