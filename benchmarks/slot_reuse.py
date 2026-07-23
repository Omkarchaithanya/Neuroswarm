#!/usr/bin/env python3
"""Multi-turn slot reuse benchmark against llama-server HTTP API."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.common import system_snapshot, write_json


def _chat(
    base_url: str,
    messages: list[dict[str, str]],
    *,
    session_id: str = "",
    id_slot: int | None = None,
    max_tokens: int = 32,
) -> dict:
    payload: dict = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
        "cache_prompt": True,
    }
    if id_slot is not None:
        payload["id_slot"] = id_slot
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _latency_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def run_benchmark(
    *,
    base_url: str,
    sessions: int = 10,
    turns: int = 20,
    max_tokens: int = 32,
) -> dict:
    system_prompt = (
        "You are a concise assistant for NeuroSwarm Axion benchmarks. "
        "Answer in one short sentence."
    )
    turn1_latencies: list[float] = []
    turn2plus_latencies: list[float] = []
    cached_tokens: list[int] = []
    errors: list[str] = []

    for s in range(sessions):
        session_id = f"sess-{s}"
        id_slot: int | None = None
        for turn in range(turns):
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Session {session_id} turn {turn}: summarize slot reuse.",
                },
            ]
            t0 = time.perf_counter()
            try:
                raw = _chat(
                    base_url,
                    messages,
                    session_id=session_id,
                    id_slot=id_slot,
                    max_tokens=max_tokens,
                )
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
                errors.append(f"{session_id}:turn{turn}:{exc}")
                break
            elapsed = _latency_ms(t0)
            if turn == 0:
                turn1_latencies.append(elapsed)
            else:
                turn2plus_latencies.append(elapsed)
            if isinstance(raw.get("id_slot"), int):
                id_slot = int(raw["id_slot"])
            usage = raw.get("usage") or {}
            details = usage.get("prompt_tokens_details") or {}
            if isinstance(details, dict):
                cached = details.get("cached_tokens")
                if isinstance(cached, int):
                    cached_tokens.append(cached)

    def _p50(values: list[float]) -> float:
        return statistics.median(values) if values else 0.0

    turn1_p50 = _p50(turn1_latencies)
    turn2_p50 = _p50(turn2plus_latencies)
    improvement = 0.0
    if turn1_p50 > 0 and turn2_p50 > 0:
        improvement = (turn1_p50 - turn2_p50) / turn1_p50

    return {
        "status": "ok" if not errors else "partial",
        "base_url": base_url,
        "sessions": sessions,
        "turns": turns,
        "turn1_count": len(turn1_latencies),
        "turn2plus_count": len(turn2plus_latencies),
        "turn1_latency_ms_p50": round(turn1_p50, 3),
        "turn2plus_latency_ms_p50": round(turn2_p50, 3),
        "ttft_improvement_ratio": round(improvement, 4),
        "cached_tokens_samples": len(cached_tokens),
        "cached_tokens_mean": round(
            statistics.mean(cached_tokens) if cached_tokens else 0.0, 2
        ),
        "errors": errors[:20],
        "host": system_snapshot(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Slot reuse benchmark")
    parser.add_argument(
        "--url",
        default=os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8080"),
        help="llama-server base URL",
    )
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "work" / "benchmarks" / "slot_reuse.json",
    )
    args = parser.parse_args()
    result = run_benchmark(
        base_url=args.url,
        sessions=args.sessions,
        turns=args.turns,
        max_tokens=args.max_tokens,
    )
    write_json(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
