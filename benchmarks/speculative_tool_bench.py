"""Speculative tool-call A/B bench (Nichols / Ye path).

Loads ``benchmarks/test-data/tool_prompts.jsonl`` (30 prompts).
Runs each prompt twice:
  - baseline: ``NSA_TOOL_SPEC_ENABLED=0`` (cascade then sync MCP)
  - speculative: ``NSA_TOOL_SPEC_ENABLED=1`` (SpeculativeEngine overlap)

Warms tool-output cache before the measured speculative pass by replaying
half the prompts. Emits JSON + CSV under ``benchmarks/results/``.

Default mode is in-process (real SpeculativeEngine + FakeMCP delays) so
``make bench-tool-spec`` finishes in well under 5 minutes on Axion.
Optional ``--live`` hits ``NSA_GATEWAY_URL`` / ``http://127.0.0.1:8000``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
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

from neuroswarm_arm.metrics.compat import MetricsStore
from neuroswarm_arm.runtime.dipa.speculative.engine import SpeculativeEngine
from neuroswarm_arm.runtime.dipa.speculative.executor import SpeculativeExecutor
from neuroswarm_arm.runtime.dipa.speculative.predictor import ToolPrediction
from neuroswarm_arm.runtime.dipa.speculative.tool_cache import ToolOutputCache
from neuroswarm_arm.schemas import ChatRequest, ChatResponse, Message

try:
    from common import system_snapshot, write_json
except ImportError:  # pragma: no cover
    def write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def system_snapshot() -> dict[str, object]:
        return {"ts": time.time()}


PROMPTS_PATH = Path(__file__).resolve().parent / "test-data" / "tool_prompts.jsonl"
DEFAULT_OUT = REPO_ROOT / "benchmarks" / "results" / "speculative_tool_bench.json"

# Synthetic cascade/MCP timings (ms) — keep total wall << 5 min for 30×2 + warm.
CASCADE_DELAY_S = float(os.getenv("NSA_TOOL_SPEC_BENCH_CASCADE_S", "0.080"))
MCP_DELAY_S = float(os.getenv("NSA_TOOL_SPEC_BENCH_MCP_S", "0.050"))
PRED_DELAY_S = float(os.getenv("NSA_TOOL_SPEC_BENCH_PRED_S", "0.005"))
# Axion c4a-standard-8 placeholder $/hr for tokens_per_dollar_delta.
HOURLY_USD = float(os.getenv("NSA_VM_HOURLY_COST_USD", "0.50"))
# Assume ~32 completion tokens per tool-roundtrip for economics delta.
TOKENS_PER_PROMPT = float(os.getenv("NSA_TOOL_SPEC_BENCH_TOKENS", "32"))


# ---------------------------------------------------------------------------
# In-proc fakes
# ---------------------------------------------------------------------------


class OraclePredictor:
    """Predicts expected tool for cache_hit_likely rows; wrong args otherwise."""

    def __init__(self, row: dict[str, Any], *, delay_s: float = PRED_DELAY_S) -> None:
        self.row = row
        self.delay_s = delay_s
        self.last: list[ToolPrediction] = []

    async def predict(self, messages: list[dict]) -> list[ToolPrediction]:
        del messages
        await asyncio.sleep(self.delay_s)
        name = str(self.row["tool_name"])
        args = dict(self.row.get("args") or {})
        if bool(self.row.get("cache_hit_likely", True)):
            pred = ToolPrediction(tool_name=name, args=args, confidence=0.95)
        else:
            # Wrong args → key mismatch → miss / sync fallthrough (cache-miss-likely).
            bad = dict(args)
            if "text" in bad:
                bad["text"] = f"wrong-{bad['text']}"
            elif "query" in bad:
                bad["query"] = f"wrong-{bad['query']}"
            elif "a" in bad:
                bad["a"] = float(bad["a"]) + 1.0
            else:
                bad["_noise"] = "1"
            pred = ToolPrediction(tool_name=name, args=bad, confidence=0.90)
        self.last = [pred]
        return self.last


class TimedCascade:
    def __init__(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        delay_s: float = CASCADE_DELAY_S,
    ) -> None:
        self.tool_name = tool_name
        self.tool_args = dict(tool_args)
        self.delay_s = delay_s

    async def generate(self, request: ChatRequest) -> ChatResponse:
        del request
        await asyncio.sleep(self.delay_s)
        return ChatResponse(
            model="cascade-bench",
            tier_used=2,
            content="cascade-pending",
            thinking_token_cap=256,
            tool_calls=[
                {
                    "type": "function",
                    "function": {
                        "name": self.tool_name,
                        "arguments": self.tool_args,
                    },
                }
            ],
            metrics={},
        )


class TimedMCP:
    def __init__(self, *, delay_s: float = MCP_DELAY_S) -> None:
        self.delay_s = delay_s
        self.calls = 0

    async def execute(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> Any:
        del kwargs
        self.calls += 1
        await asyncio.sleep(self.delay_s)
        return {"ok": True, "tool": tool_name, "args": args}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_prompts(path: Path = PROMPTS_PATH) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    if len(rows) < 30:
        raise RuntimeError(f"expected ≥30 prompts in {path}, got {len(rows)}")
    return rows


def _percentile(vals: list[float], pct: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] * (c - k) + s[c] * (k - f))


def _args_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True, separators=(",", ":")) == json.dumps(
        b, sort_keys=True, separators=(",", ":")
    )


async def _baseline_latency(row: dict[str, Any]) -> float:
    """Sync path: cascade then MCP (no overlap)."""
    os.environ["NSA_TOOL_SPEC_ENABLED"] = "0"
    cascade = TimedCascade(
        tool_name=str(row["tool_name"]),
        tool_args=dict(row.get("args") or {}),
    )
    mcp = TimedMCP()
    t0 = time.perf_counter()
    resp = await cascade.generate(
        ChatRequest(messages=[Message(role="user", content=str(row["prompt"]))])
    )
    assert resp.tool_calls
    await mcp.execute(str(row["tool_name"]), dict(row.get("args") or {}))
    return (time.perf_counter() - t0) * 1000.0


async def _speculative_once(
    row: dict[str, Any],
    *,
    cache: ToolOutputCache,
    metrics: MetricsStore,
) -> dict[str, Any]:
    """One SpeculativeEngine generate; return latency + flags."""
    os.environ["NSA_TOOL_SPEC_ENABLED"] = "1"
    predictor = OraclePredictor(row)
    cascade = TimedCascade(
        tool_name=str(row["tool_name"]),
        tool_args=dict(row.get("args") or {}),
    )
    mcp = TimedMCP()
    executor = SpeculativeExecutor(
        mcp, cache, asyncio.Semaphore(4), tool_timeout_s=5.0
    )
    expected_key = cache.make_key(str(row["tool_name"]), dict(row.get("args") or {}))
    # True when ToolOutputCache served the *correct* tool key (spec hit or sync fallthrough).
    cache_hit_flag = {"value": False}
    orig = executor.speculate

    async def _tracked(pred: ToolPrediction) -> Any:
        task = await orig(pred)
        if task.key == expected_key and task.cache_hit_on_dispatch:
            cache_hit_flag["value"] = True
        return task

    executor.speculate = _tracked  # type: ignore[method-assign]
    eng = SpeculativeEngine(
        predictor,
        executor,
        cascade,
        cache,
        metrics,
        tool_timeout_s=5.0,
        threshold=0.75,
    )
    req = ChatRequest(messages=[Message(role="user", content=str(row["prompt"]))])
    t0 = time.perf_counter()
    resp = await eng.generate(req)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    predicted_correct = False
    if predictor.last:
        p = predictor.last[0]
        predicted_correct = p.tool_name == str(row["tool_name"]) and _args_equal(
            dict(p.args), dict(row.get("args") or {})
        )

    return {
        "latency_ms": latency_ms,
        "predicted_correct": predicted_correct,
        "cache_hit": bool(cache_hit_flag["value"]),
        "speculative_hit": bool(getattr(resp, "speculative_hit", False)),
        "saved_ms_engine": float(getattr(resp, "speculative_latency_saved_ms", 0.0) or 0.0),
    }


async def run_inproc(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = MetricsStore()
    cache = ToolOutputCache(max_size=1024, ttl_seconds=600)

    # Baseline pass (spec off).
    baseline_ms: list[float] = []
    for row in prompts:
        baseline_ms.append(await _baseline_latency(row))

    # Warm: replay first half with speculative on (populate ToolOutputCache).
    warm_n = max(1, len(prompts) // 2)
    warm_rows = prompts[:warm_n]
    for row in warm_rows:
        # Force correct prediction during warm so keys land in cache.
        warm_row = dict(row)
        warm_row["cache_hit_likely"] = True
        await _speculative_once(warm_row, cache=cache, metrics=metrics)

    # Measured speculative pass.
    rows_out: list[dict[str, Any]] = []
    for i, row in enumerate(prompts):
        spec = await _speculative_once(row, cache=cache, metrics=metrics)
        base = baseline_ms[i]
        saved = max(0.0, base - float(spec["latency_ms"]))
        rows_out.append(
            {
                "id": row.get("id"),
                "style": row.get("style"),
                "prompt": row.get("prompt"),
                "tool_name": row["tool_name"],
                "predicted_correct": bool(spec["predicted_correct"]),
                "cache_hit": bool(spec["cache_hit"]),
                "speculative_hit": bool(spec["speculative_hit"]),
                "latency_baseline_ms": round(base, 3),
                "latency_speculative_ms": round(float(spec["latency_ms"]), 3),
                "time_saved_ms": round(saved, 3),
                "cache_hit_likely": bool(row.get("cache_hit_likely", False)),
                "warmed": i < warm_n,
            }
        )

    return _summarize(rows_out, mode="inproc", warm_n=warm_n, cache_metrics=cache.metrics())


def _summarize(
    rows_out: list[dict[str, Any]],
    *,
    mode: str,
    warm_n: int,
    cache_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    saved = [float(r["time_saved_ms"]) for r in rows_out]
    hits = sum(1 for r in rows_out if r.get("cache_hit"))
    n = len(rows_out) or 1
    hit_rate = hits / n
    avg_saved = statistics.mean(saved) if saved else 0.0
    p50 = _percentile(saved, 50)
    p95 = _percentile(saved, 95)

    mean_base = statistics.mean(float(r["latency_baseline_ms"]) for r in rows_out)
    mean_spec = statistics.mean(float(r["latency_speculative_ms"]) for r in rows_out)
    # tokens/$ delta: apply measured latency speedup to a reference Axion tokens/$
    # (prometheus runtime_tokens_per_dollar ~12.5k). Avoids absurd synthetic tpd
    # from millisecond FakeMCP timings.
    ref_tpd = float(os.getenv("NSA_TOOL_SPEC_REF_TPD", "12580"))
    speedup = (mean_base / mean_spec) if mean_spec > 0 else 1.0
    tpd_base = ref_tpd
    tpd_spec = ref_tpd * speedup
    tpd_delta = tpd_spec - tpd_base

    return {
        "status": "ok",
        "mode": mode,
        "system": system_snapshot(),
        "config": {
            "prompts": n,
            "warm_n": warm_n,
            "cascade_delay_s": CASCADE_DELAY_S,
            "mcp_delay_s": MCP_DELAY_S,
            "hourly_usd": HOURLY_USD,
            "tokens_per_prompt": TOKENS_PER_PROMPT,
            "ref_tokens_per_dollar": float(os.getenv("NSA_TOOL_SPEC_REF_TPD", "12580")),
            "nsa_tool_spec_threshold": os.getenv("NSA_TOOL_SPEC_THRESHOLD", "0.75"),
        },
        "summary": {
            "hit_rate": round(hit_rate, 4),
            "avg_time_saved_ms": round(avg_saved, 3),
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "tokens_per_dollar_delta": round(tpd_delta, 2),
            "mean_latency_baseline_ms": round(mean_base, 3),
            "mean_latency_speculative_ms": round(mean_spec, 3),
            "predicted_correct_rate": round(
                sum(1 for r in rows_out if r.get("predicted_correct")) / n, 4
            ),
            "latency_speedup": round(speedup, 4),
            "tokens_per_dollar_baseline": round(tpd_base, 2),
            "tokens_per_dollar_speculative": round(tpd_spec, 2),
        },
        "cache": cache_metrics or {},
        "prompts": rows_out,
    }


async def run_live(prompts: list[dict[str, Any]], base_url: str) -> dict[str, Any]:
    """Optional live gateway path (slower; still warms half first)."""
    import httpx

    url = base_url.rstrip("/") + "/v1/chat/completions"

    async def _chat(client: httpx.AsyncClient, prompt: str) -> tuple[float, dict[str, Any]]:
        payload = {
            "model": "cascade",
            "messages": [{"role": "user", "content": prompt}],
        }
        t0 = time.perf_counter()
        res = await client.post(url, json=payload, timeout=120.0)
        ms = (time.perf_counter() - t0) * 1000.0
        res.raise_for_status()
        return ms, res.json()

    rows_out: list[dict[str, Any]] = []
    warm_n = max(1, len(prompts) // 2)

    async with httpx.AsyncClient() as client:
        # Baseline: ask gateway with header override if supported; else sequential.
        # Live mode relies on gateway already running; env toggle needs process restart,
        # so we measure wall latency twice and read speculative_* from response body.
        baseline_ms: list[float] = []
        for row in prompts:
            ms, _body = await _chat(client, str(row["prompt"]))
            baseline_ms.append(ms)

        for row in prompts[:warm_n]:
            await _chat(client, str(row["prompt"]))

        for i, row in enumerate(prompts):
            ms, body = await _chat(client, str(row["prompt"]))
            metrics = body.get("metrics") or {}
            cache_hit = bool(
                body.get("speculative_hit")
                or metrics.get("cache_hit")
                or metrics.get("speculative_hit")
            )
            base = baseline_ms[i]
            rows_out.append(
                {
                    "id": row.get("id"),
                    "style": row.get("style"),
                    "prompt": row.get("prompt"),
                    "tool_name": row["tool_name"],
                    "predicted_correct": None,
                    "cache_hit": cache_hit,
                    "speculative_hit": bool(body.get("speculative_hit")),
                    "latency_baseline_ms": round(base, 3),
                    "latency_speculative_ms": round(ms, 3),
                    "time_saved_ms": round(max(0.0, base - ms), 3),
                    "cache_hit_likely": bool(row.get("cache_hit_likely", False)),
                    "warmed": i < warm_n,
                }
            )

    return _summarize(rows_out, mode="live", warm_n=warm_n)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "style",
        "tool_name",
        "predicted_correct",
        "cache_hit",
        "latency_baseline_ms",
        "latency_speculative_ms",
        "time_saved_ms",
        "cache_hit_likely",
        "warmed",
        "prompt",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="Speculative tool-call A/B benchmark")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--prompts", type=Path, default=PROMPTS_PATH)
    ap.add_argument(
        "--live",
        action="store_true",
        help="Hit live gateway (slower). Default: in-process SpeculativeEngine.",
    )
    ap.add_argument(
        "--gateway-url",
        default=os.getenv("NSA_GATEWAY_URL", "http://127.0.0.1:8000"),
    )
    args = ap.parse_args()

    prompts = load_prompts(args.prompts)
    if args.live:
        payload = asyncio.run(run_live(prompts, args.gateway_url))
    else:
        payload = asyncio.run(run_inproc(prompts))

    out: Path = args.out
    write_json(out, payload)
    csv_path = out.with_suffix(".csv")
    write_csv(csv_path, list(payload.get("prompts") or []))
    summary = payload.get("summary") or {}
    print(json.dumps({"out": str(out), "csv": str(csv_path), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
