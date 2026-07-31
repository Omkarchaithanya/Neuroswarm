"""Offline AROP v1 proof: 3 dry-run cycles → work/evidence/arop-v1/."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from neuroswarm_arm.arop.evolve_cycle import run_cycle
from neuroswarm_arm.arop.history import read_history
from neuroswarm_arm.arop.metrics_parser import load_json
from neuroswarm_arm.arop.policy_state import PolicyState, load_policy, save_policy

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "arop" / "fixtures"
EVID = ROOT / "work" / "evidence" / "arop-v1"


def main() -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    policy_path = EVID / "policy_state.yaml"
    hist = EVID / "history.jsonl"
    if hist.exists():
        hist.unlink()
    save_policy(PolicyState(8, 0.7, 4096), policy_path)
    metrics_text = (FIX / "llama_metrics.txt").read_text(encoding="utf-8")

    r1 = run_cycle(
        dry_run=True,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIX / "code_hotspots_apx.json",
        instruction_mix_path=FIX / "instruction_mix_apx.json",
        acceptance_path=FIX / "acceptance_low_t1.json",
        governor_path=FIX / "governor_overrun.json",
        tier_metrics_text=metrics_text,
    )
    r2 = run_cycle(
        dry_run=True,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIX / "code_hotspots_contaminated.json",
        acceptance_path=FIX / "acceptance_low_t1.json",
        tier_metrics_text=metrics_text,
    )
    payload = load_json(FIX / "acceptance_low_t1.json")
    for i, row in enumerate(payload["per_request"]):
        row["tier_used"] = 1 if i < 7 else 2
    payload["avg_latency_ms"] = 5000.0
    acc = EVID / "acceptance_r3.json"
    acc.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    r3 = run_cycle(
        dry_run=True,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIX / "code_hotspots_apx.json",
        acceptance_path=acc,
        governor_path=FIX / "governor_overrun.json",
        tier_metrics_text=metrics_text,
    )

    rows = read_history(hist)
    work_hist = ROOT / "work" / "arop" / "history.jsonl"
    work_hist.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(hist, work_hist)

    lines = [
        "# AROP v1 dry-run proof (offline fixtures)",
        "",
        "Three dry-run cycles against fixture JSON derived from real apx captures.",
        "No live Axion apply. No invented improvement percentages.",
        "",
        "| Cycle | Rule | Outcome | Param | Before → After |",
        "|-------|------|---------|-------|----------------|",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"| {i} | {row.get('rule_id')} | {row.get('outcome')} | "
            f"{row.get('param')} | {row.get('before')} → {row.get('after')} |"
        )
    lines.extend(["", "## Rationale", ""])
    for i, r in enumerate([r1, r2, r3], 1):
        lines.append(f"{i}. **{r.decision.rule_id}**: {r.decision.rationale}")
    lines.extend(["", "## history.jsonl", "", "```", hist.read_text(encoding="utf-8").rstrip(), "```", ""])
    (EVID / "MEASURED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(hist.read_text(encoding="utf-8"))
    restored = load_policy(policy_path)
    print(f"Wrote {EVID / 'MEASURED.md'}")
    print(f"policy unchanged after dry-run: cascade_draft_k={restored.cascade_draft_k}")


if __name__ == "__main__":
    main()
