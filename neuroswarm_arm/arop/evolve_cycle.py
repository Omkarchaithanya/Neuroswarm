"""AROP evolve cycle orchestrator — dry-run by default; --apply for live gateway restart."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from neuroswarm_arm.arop.history import append_history
from neuroswarm_arm.arop.metrics_parser import MetricsBundle, collect_bundle
from neuroswarm_arm.arop.policy_state import (
    DEFAULT_POLICY_PATH,
    PolicyState,
    load_policy,
    save_policy,
    write_gateway_env_overrides,
)
from neuroswarm_arm.arop.tuner import Decision, apply_decision, decide

LOG = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class CycleResult:
    decision: Decision
    outcome: str
    policy_before: dict[str, Any]
    policy_after: dict[str, Any]
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any] | None
    history_path: Path


def _regression(
    before: MetricsBundle,
    after: MetricsBundle,
    max_pct: float,
) -> str | None:
    """Return reason string if tok/s or tier1 hit-rate regresses > max_pct, else None."""
    if before.throughput is not None and after.throughput is not None:
        b = before.throughput.predicted_tokens_seconds
        a = after.throughput.predicted_tokens_seconds
        if b > 0 and (b - a) / b > max_pct / 100.0:
            return (
                f"tok/s regression: {b:.4f}→{a:.4f} "
                f"({(b - a) / b * 100:.1f}% > {max_pct}%)"
            )
    if before.cascade is not None and after.cascade is not None:
        b = before.cascade.tier1_hit_rate
        a = after.cascade.tier1_hit_rate
        if b > 0 and (b - a) / b > max_pct / 100.0:
            return (
                f"tier1_hit_rate regression: {b:.4f}→{a:.4f} "
                f"({(b - a) / b * 100:.1f}% > {max_pct}%)"
            )
    return None


def restart_gateway(*, compose_file: Path | None = None) -> None:
    """Restart only the gateway service (ASCR knobs are gateway-side)."""
    compose = compose_file or (REPO_ROOT / "docker-compose.yaml")
    cmd = ["docker", "compose", "-f", str(compose), "restart", "gateway"]
    LOG.info("restarting gateway: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def run_cycle(
    *,
    dry_run: bool = True,
    policy_path: Path | None = None,
    history_path: Path | None = None,
    hotspots_path: Path | None = None,
    instruction_mix_path: Path | None = None,
    acceptance_path: Path | None = None,
    governor_path: Path | None = None,
    tier_metrics_url: str | None = None,
    tier_metrics_text: str | None = None,
    max_regression_pct: float = 5.0,
    env_override_path: Path | None = None,
    restart_fn: Callable[[], None] | None = None,
    recapture_fn: Callable[[], MetricsBundle] | None = None,
    allow_demo: bool | None = None,
) -> CycleResult:
    """One AROP cycle. Default dry_run=True — compute + log, do not apply."""
    if allow_demo is None:
        allow_demo = os.getenv("NSA_PERFORMIX_ALLOW_DEMO", "0") not in {
            "0",
            "false",
            "False",
            "no",
            "NO",
            "",
        }
    if not dry_run and allow_demo:
        raise RuntimeError(
            "live --apply refused: NSA_PERFORMIX_ALLOW_DEMO must be 0 "
            "(demo/synthetic telemetry is dishonest)"
        )

    policy_file = policy_path or DEFAULT_POLICY_PATH
    hist = history_path or Path("work/arop/history.jsonl")
    policy = load_policy(policy_file)
    policy_before = policy.to_dict()

    bundle = collect_bundle(
        hotspots_path=hotspots_path,
        instruction_mix_path=instruction_mix_path,
        acceptance_path=acceptance_path,
        governor_path=governor_path,
        tier_metrics_url=tier_metrics_url,
        tier_metrics_text=tier_metrics_text,
    )
    decision = decide(bundle, policy)
    metrics_before = dict(decision.metrics_used)

    # Non-change outcomes (skip / hold / metric unavailable)
    if decision.action != "change":
        outcome = {
            "skip": "skipped_contaminated",
            "metric_unavailable": "metric_unavailable",
            "hold": "hold",
        }.get(decision.action, decision.action)
        append_history(
            {
                "rule_id": decision.rule_id,
                "param": decision.param,
                "before": decision.before,
                "after": decision.after,
                "rationale": decision.rationale,
                "metrics_before": metrics_before,
                "metrics_after": None,
                "outcome": outcome,
                "dry_run": dry_run,
                "policy_before": policy_before,
                "policy_after": policy_before,
            },
            path=hist,
        )
        return CycleResult(
            decision=decision,
            outcome=outcome,
            policy_before=policy_before,
            policy_after=policy_before,
            metrics_before=metrics_before,
            metrics_after=None,
            history_path=hist,
        )

    # decision.action == "change"
    if dry_run:
        append_history(
            {
                "rule_id": decision.rule_id,
                "param": decision.param,
                "before": decision.before,
                "after": decision.after,
                "rationale": decision.rationale,
                "metrics_before": metrics_before,
                "metrics_after": None,
                "outcome": "dry_run",
                "dry_run": True,
                "policy_before": policy_before,
                "policy_after": apply_decision(policy, decision).to_dict(),
            },
            path=hist,
        )
        return CycleResult(
            decision=decision,
            outcome="dry_run",
            policy_before=policy_before,
            policy_after=apply_decision(policy, decision).to_dict(),
            metrics_before=metrics_before,
            metrics_after=None,
            history_path=hist,
        )

    # Live apply path
    snapshot = policy_file.with_suffix(policy_file.suffix + ".snapshot")
    shutil.copy2(policy_file, snapshot)
    new_policy = apply_decision(policy, decision)
    save_policy(new_policy, policy_file)
    env_path = env_override_path or Path("work/arop/gateway_overrides.env")
    write_gateway_env_overrides(new_policy, env_path)

    try:
        (restart_fn or restart_gateway)()
        if recapture_fn is None:
            raise RuntimeError(
                "live --apply requires recapture_fn (or offline fixtures) "
                "to compare before/after metrics"
            )
        after_bundle = recapture_fn()
        after_decision = decide(after_bundle, new_policy)
        metrics_after = dict(after_decision.metrics_used)
        reason = _regression(bundle, after_bundle, max_regression_pct)
        if reason:
            LOG.warning("regression detected — rolling back: %s", reason)
            shutil.copy2(snapshot, policy_file)
            write_gateway_env_overrides(policy, env_path)
            (restart_fn or restart_gateway)()
            append_history(
                {
                    "rule_id": decision.rule_id,
                    "param": decision.param,
                    "before": decision.before,
                    "after": decision.after,
                    "rationale": decision.rationale,
                    "metrics_before": metrics_before,
                    "metrics_after": metrics_after,
                    "outcome": "rolled_back",
                    "rollback_reason": reason,
                    "dry_run": False,
                    "policy_before": policy_before,
                    "policy_after": policy_before,
                },
                path=hist,
            )
            return CycleResult(
                decision=decision,
                outcome="rolled_back",
                policy_before=policy_before,
                policy_after=policy_before,
                metrics_before=metrics_before,
                metrics_after=metrics_after,
                history_path=hist,
            )

        append_history(
            {
                "rule_id": decision.rule_id,
                "param": decision.param,
                "before": decision.before,
                "after": decision.after,
                "rationale": decision.rationale,
                "metrics_before": metrics_before,
                "metrics_after": metrics_after,
                "outcome": "applied",
                "dry_run": False,
                "policy_before": policy_before,
                "policy_after": new_policy.to_dict(),
            },
            path=hist,
        )
        return CycleResult(
            decision=decision,
            outcome="applied",
            policy_before=policy_before,
            policy_after=new_policy.to_dict(),
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            history_path=hist,
        )
    except Exception:
        LOG.exception("apply failed — restoring policy snapshot")
        if snapshot.is_file():
            shutil.copy2(snapshot, policy_file)
        raise
    finally:
        if snapshot.is_file():
            snapshot.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AROP v1 rule-based cascade tuner (dry-run default)"
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute and log proposed change without applying (default: true). "
        "Use --no-dry-run or --apply for live mode.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Alias for --no-dry-run (live apply + gateway restart).",
    )
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--history", type=Path, default=Path("work/arop/history.jsonl"))
    parser.add_argument("--hotspots", type=Path, default=None)
    parser.add_argument("--instruction-mix", type=Path, default=None)
    parser.add_argument("--acceptance", type=Path, default=None)
    parser.add_argument("--governor", type=Path, default=None)
    parser.add_argument(
        "--tier-metrics-url",
        default=None,
        help="llama-server base URL for /metrics (e.g. http://127.0.0.1:8081)",
    )
    parser.add_argument("--max-regression-pct", type=float, default=5.0)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    dry_run = False if args.apply else bool(args.dry_run)
    result = run_cycle(
        dry_run=dry_run,
        policy_path=args.policy,
        history_path=args.history,
        hotspots_path=args.hotspots,
        instruction_mix_path=args.instruction_mix,
        acceptance_path=args.acceptance,
        governor_path=args.governor,
        tier_metrics_url=args.tier_metrics_url,
        max_regression_pct=args.max_regression_pct,
    )
    print(
        f"outcome={result.outcome} rule={result.decision.rule_id} "
        f"param={result.decision.param} "
        f"{result.decision.before}→{result.decision.after}"
    )
    print(f"rationale: {result.decision.rationale}")
    print(f"history: {result.history_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
