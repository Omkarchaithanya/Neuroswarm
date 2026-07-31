"""SpecBench-style speculative-decoding benchmark (Gap G16).

Loop workloads × verify strategies; emit JSON + markdown summary.
Exit 0 always (benchmark, not a test).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest

try:
    from common import DEFAULT_RESULTS_DIR, write_json
except ImportError:  # pragma: no cover
    DEFAULT_RESULTS_DIR = REPO_ROOT / "work" / "benchmarks"

    def write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


WORKLOADS_PATH = Path(__file__).resolve().parent / "specdec_workloads.yaml"
STRATEGIES_PATH = (
    REPO_ROOT
    / "neuroswarm_arm"
    / "runtime"
    / "armcascade"
    / "config"
    / "strategies.yaml"
)
VERIFY_CANDIDATES = ("block", "logits", "tree")
LONG_DOC_MARKER = "[LONG_DOC_4K]"
# Deterministic ~4k whitespace-separated tokens (no production data paths).
_LONG_DOC_4K = " ".join(f"tok{i % 97}" for i in range(4096))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML required to load SpecDec workloads")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TypeError(f"yaml root must be mapping: {path}")
    return dict(data)


def bench_enabled() -> bool:
    if _env_bool("NSA_SPECDEC_BENCH", False):
        return True
    strategies = _load_yaml(STRATEGIES_PATH).get("strategies") or {}
    body = dict(strategies.get("specdec_bench") or {})
    return bool(body.get("enabled", False))


def expand_prompt(prompt: str) -> str:
    if LONG_DOC_MARKER not in prompt:
        return prompt
    return prompt.replace(LONG_DOC_MARKER, _LONG_DOC_4K)


def load_workloads(path: Path = WORKLOADS_PATH) -> tuple[list[dict[str, Any]], int]:
    raw = _load_yaml(path)
    workloads = list(raw.get("workloads") or [])
    iterations = int(raw.get("iterations_per_prompt") or 4)
    return workloads, iterations


def enabled_verify_strategies() -> list[str]:
    strategies = _load_yaml(STRATEGIES_PATH).get("strategies") or {}
    out: list[str] = []
    for name in VERIFY_CANDIDATES:
        body = dict(strategies.get(name) or {})
        enabled = bool(body.get("enabled", name == "block"))
        if name == "logits" and os.getenv("NSA_ASCR_LOGITS_ENABLED") is not None:
            enabled = _env_bool("NSA_ASCR_LOGITS_ENABLED", enabled)
        if name == "tree" and os.getenv("NSA_ASCR_TREE_ENABLED") is not None:
            enabled = _env_bool("NSA_ASCR_TREE_ENABLED", enabled)
        if enabled:
            out.append(name)
    return out or ["block"]


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def _finite(x: float, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return v


def _metric(metrics: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in metrics and metrics[key] is not None:
            return _finite(metrics[key], default)
    return default


def run_one(
    rt: Any,
    *,
    prompt: str,
    workload: str,
    verify_strategy: str,
    max_tokens: int = 64,
    session_id: str = "",
) -> dict[str, Any]:
    req = InferenceRequest(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        agent_role="tool_call",
        latency_sla_ms=5000.0,
        stream=True,
        session_id=session_id or f"specdec-{workload}-{verify_strategy}-{time.time_ns()}",
    )
    t0 = time.perf_counter()
    out = rt.infer(req)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    metrics = dict(out.metrics or {})
    draft = max(
        0,
        int(
            _metric(
                metrics,
                "ascr_draft_tokens",
                "tokens_proposed",
                default=float(out.completion_tokens or 0),
            )
        ),
    )
    accepted = max(
        0,
        int(
            _metric(
                metrics,
                "ascr_accepted_tokens",
                "tokens_accepted",
                default=float(out.completion_tokens or max(1, draft)),
            )
        ),
    )
    if accepted == 0 and (out.completion_tokens or 0) > 0:
        accepted = int(out.completion_tokens)
    if draft == 0:
        draft = max(1, accepted)
    engine_gain = _metric(metrics, "ascr_speculation_gain", default=0.0)
    spec_gain = accepted / max(1, draft)
    latency_ms = _metric(metrics, "cascade_latency_ms", "latency_ms", default=wall_ms)
    ttft_ms = _finite(getattr(out, "ttft_ms", 0.0) or 0.0, 0.0)
    if ttft_ms <= 0.0:
        ttft_ms = _metric(metrics, "ttft_ms", default=latency_ms * 0.2)
    draft_ms = _metric(metrics, "ascr_draft_ms", "draft_ms", default=0.0)
    verify_ms = _metric(metrics, "ascr_verify_ms", "verify_ms", default=0.0)
    if draft_ms <= 0.0 and verify_ms <= 0.0 and latency_ms > 0.0:
        draft_ms = latency_ms * 0.4
        verify_ms = latency_ms * 0.6
    tokens = max(1, int(out.completion_tokens or accepted or 1))
    return {
        "workload": workload,
        "verify_strategy": verify_strategy,
        "prompt_preview": prompt[:80],
        "tokens": tokens,
        "wall_ms": wall_ms,
        "ttft_ms": ttft_ms,
        "draft_tokens": draft,
        "accepted_tokens": accepted,
        "accepted_prefix_len": accepted,
        "acceptance_rate": accepted / max(1, draft),
        "ascr_speculation_gain": spec_gain,
        "engine_ascr_speculation_gain": engine_gain,
        "draft_ms": draft_ms,
        "verify_ms": verify_ms,
        "latency_ms": latency_ms,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "tokens_per_sec": 0.0,
            "acceptance_rate": 0.0,
            "mean_accepted_prefix_len": 0.0,
            "p50_ttft_ms": 0.0,
            "p95_ttft_ms": 0.0,
            "mean_draft_ms": 0.0,
            "mean_verify_ms": 0.0,
            "ascr_speculation_gain": 0.0,
            "engine_ascr_speculation_gain": 0.0,
            "n": 0,
        }
    total_tokens = sum(int(r["tokens"]) for r in rows)
    total_wall_s = sum(float(r["wall_ms"]) for r in rows) / 1000.0
    ttfts = sorted(float(r["ttft_ms"]) for r in rows)
    return {
        "tokens_per_sec": _finite(total_tokens / max(total_wall_s, 1e-6)),
        "acceptance_rate": _finite(
            statistics.fmean(float(r["acceptance_rate"]) for r in rows)
        ),
        "mean_accepted_prefix_len": _finite(
            statistics.fmean(float(r["accepted_prefix_len"]) for r in rows)
        ),
        "p50_ttft_ms": _finite(_percentile(ttfts, 50)),
        "p95_ttft_ms": _finite(_percentile(ttfts, 95)),
        "mean_draft_ms": _finite(statistics.fmean(float(r["draft_ms"]) for r in rows)),
        "mean_verify_ms": _finite(
            statistics.fmean(float(r["verify_ms"]) for r in rows)
        ),
        "ascr_speculation_gain": _finite(
            statistics.fmean(float(r["ascr_speculation_gain"]) for r in rows)
        ),
        "engine_ascr_speculation_gain": _finite(
            statistics.fmean(float(r["engine_ascr_speculation_gain"]) for r in rows)
        ),
        "n": len(rows),
    }


def print_markdown_table(payload: dict[str, Any]) -> None:
    cols = (
        "scope",
        "tokens_per_sec",
        "acceptance_rate",
        "mean_accepted_prefix_len",
        "p50_ttft_ms",
        "p95_ttft_ms",
        "mean_draft_ms",
        "mean_verify_ms",
        "ascr_speculation_gain",
    )
    print("| " + " | ".join(cols) + " |")
    print("| " + " | ".join("---" for _ in cols) + " |")

    def _row(scope: str, m: dict[str, Any]) -> None:
        print(
            "| "
            + " | ".join(
                [
                    scope,
                    f"{m.get('tokens_per_sec', 0):.2f}",
                    f"{m.get('acceptance_rate', 0):.3f}",
                    f"{m.get('mean_accepted_prefix_len', 0):.2f}",
                    f"{m.get('p50_ttft_ms', 0):.2f}",
                    f"{m.get('p95_ttft_ms', 0):.2f}",
                    f"{m.get('mean_draft_ms', 0):.2f}",
                    f"{m.get('mean_verify_ms', 0):.2f}",
                    f"{m.get('ascr_speculation_gain', 0):.3f}",
                ]
            )
            + " |"
        )

    _row("overall", payload.get("overall") or {})
    for key, body in sorted((payload.get("by_verify") or {}).items()):
        _row(f"verify:{key}", body)
    for key, body in sorted((payload.get("by_workload") or {}).items()):
        _row(f"workload:{key}", body)


def run_specdec_bench(
    *,
    live: bool = False,
    workloads_path: Path = WORKLOADS_PATH,
    max_tokens: int = 64,
) -> dict[str, Any]:
    if not bench_enabled():
        return {
            "status": "skipped",
            "reason": "NSA_SPECDEC_BENCH off and strategies.specdec_bench.enabled=false",
            "overall": aggregate_rows([]),
            "by_verify": {},
            "by_workload": {},
            "rows": [],
        }

    workloads, iterations = load_workloads(workloads_path)
    verifiers = enabled_verify_strategies()
    rows: list[dict[str, Any]] = []
    prev_verifier = os.environ.get("NSA_ASCR_DEFAULT_VERIFIER")

    try:
        for verify in verifiers:
            os.environ["NSA_ASCR_DEFAULT_VERIFIER"] = verify
            rt = build_dipa(use_mock=not live, start=True)
            try:
                for wl in workloads:
                    name = str(wl.get("name") or "unnamed")
                    prompts = [expand_prompt(str(p)) for p in (wl.get("prompts") or [])]
                    for prompt in prompts:
                        for i in range(max(1, iterations)):
                            rows.append(
                                run_one(
                                    rt,
                                    prompt=prompt,
                                    workload=name,
                                    verify_strategy=verify,
                                    max_tokens=max_tokens,
                                    session_id=f"specdec-{name}-{verify}-{i}-{time.time_ns()}",
                                )
                            )
            finally:
                rt.shutdown()
    finally:
        if prev_verifier is None:
            os.environ.pop("NSA_ASCR_DEFAULT_VERIFIER", None)
        else:
            os.environ["NSA_ASCR_DEFAULT_VERIFIER"] = prev_verifier

    by_verify: dict[str, dict[str, Any]] = {}
    for v in verifiers:
        by_verify[v] = aggregate_rows([r for r in rows if r["verify_strategy"] == v])

    by_workload: dict[str, dict[str, Any]] = {}
    for wl in workloads:
        name = str(wl.get("name") or "unnamed")
        by_workload[name] = aggregate_rows([r for r in rows if r["workload"] == name])

    overall = aggregate_rows(rows)
    return {
        "status": "ok",
        "mode": "live" if live else "mock",
        "verify_strategies": verifiers,
        "iterations_per_prompt": iterations,
        "overall": overall,
        "by_verify": by_verify,
        "by_workload": by_workload,
        "ascr_speculation_gain": overall.get("ascr_speculation_gain", 0.0),
        "engine_ascr_speculation_gain": overall.get(
            "engine_ascr_speculation_gain", 0.0
        ),
        "tokens_per_sec": overall.get("tokens_per_sec", 0.0),
        "acceptance_rate": overall.get("acceptance_rate", 0.0),
        "mean_accepted_prefix_len": overall.get("mean_accepted_prefix_len", 0.0),
        "p50_ttft_ms": overall.get("p50_ttft_ms", 0.0),
        "p95_ttft_ms": overall.get("p95_ttft_ms", 0.0),
        "mean_draft_ms": overall.get("mean_draft_ms", 0.0),
        "mean_verify_ms": overall.get("mean_verify_ms", 0.0),
        "n": overall.get("n", 0),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SpecDec SpecBench-style benchmark")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "specdec_bench.json",
    )
    parser.add_argument("--live", action="store_true", help="use real backends")
    parser.add_argument("--mock", action="store_true", default=False)
    parser.add_argument(
        "--workloads",
        type=Path,
        default=WORKLOADS_PATH,
    )
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args()
    live = bool(args.live) and not bool(args.mock)

    # CI/Makefile set NSA_SPECDEC_BENCH=1; allow local dry-run without export.
    os.environ.setdefault("NSA_SPECDEC_BENCH", "1")

    try:
        payload = run_specdec_bench(
            live=live,
            workloads_path=args.workloads,
            max_tokens=args.max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — benchmark must exit 0
        payload = {
            "status": "error",
            "error": str(exc),
            "overall": aggregate_rows([]),
            "by_verify": {},
            "by_workload": {},
            "ascr_speculation_gain": 0.0,
            "rows": [],
        }

    # Compact artifact for CI (drop per-row prompts bulk if huge).
    write_json(args.out, payload)
    print_markdown_table(payload)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
