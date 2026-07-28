#!/usr/bin/env python3
"""Per-tier llama-server KV cache verification — curl-level evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ~400-token stable system prompt for prefix-cache proof
LONG_STABLE_SYSTEM_PROMPT = (
    "You are NeuroSwarm Axion KV-cache audit assistant. "
    "Follow these rules for every response: be concise, factual, and deterministic. "
    "Never invent hardware specs. Arm Neoverse-V2 on GCP Axion c4a-standard-8 uses "
    "SVE2, I8MM, and BF16 where enabled. KleidiAI accelerates quantized matmul on CPU. "
    "llama-server maintains per-slot transformer KV cache keyed by id_slot. "
    "cache_prompt true reuses prior prompt tokens within the same slot. "
    "Multi-turn sessions must show cached_tokens greater than zero on turn two plus. "
    "Tier one runs Qwen2.5-0.5B-Instruct-Q4_0. Tier two runs Qwen2.5-3B-Instruct-Q4_0. "
    "Tier three runs DeepSeek-R1-Distill-Qwen-7B-Q4_0. Cross-tier KV tensors are not shared. "
    "MAKS stores opaque session metadata blobs separate from in-process GGML KV. "
    "RadixSlotRouter maps token-prefix hashes to physical slots per backend. "
    "Slot persistence requires --slot-save-path on llama-server. "
    "Prometheus metrics expose kv_cache token gauges when --metrics is set. "
    "Performix apx may sample hotspots during cascade escalation on metal only. "
    "Governor caps reasoning tokens based on plan state and tool confidence. "
    "Cascade escalates when verifier confidence falls below tier acceptance threshold. "
    "Prefill on a new tier after escalation is always cold even if prior tier was warm. "
    "Document every measurement with JSON not paper claims. "
    "Honor NSA_TIER1_URL NSA_TIER2_URL NSA_TIER3_URL from environment. "
    "Repeat: answer briefly, one or two sentences maximum unless asked for detail."
)

ESCALATION_PROMPT = (
    "Solve step by step: A train leaves Station A at 9am at 60 mph. "
    "Another leaves Station B 300 miles away at 10am at 80 mph toward A. "
    "When do they meet? Show all algebra."
)

TIER_URLS = {
    1: os.getenv("NSA_TIER1_URL", "http://127.0.0.1:8081"),
    2: os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8082"),
    3: os.getenv("NSA_TIER3_URL", "http://127.0.0.1:8083"),
}

TIER_TIMEOUT_S = {
    1: float(os.getenv("KV_PROBE_TIMEOUT_TIER1", "180")),
    2: float(os.getenv("KV_PROBE_TIMEOUT_TIER2", "300")),
    3: float(os.getenv("KV_PROBE_TIMEOUT_TIER3", "600")),
}


def _get(url: str, timeout: float = 10.0) -> tuple[int, str, Any]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                body: Any = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = raw
            return resp.status, raw, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = raw
        return exc.code, raw, body
    except urllib.error.URLError as exc:
        return 0, str(exc.reason), {"error": str(exc.reason)}


def _post_json(url: str, payload: dict[str, Any], timeout: float = 120.0) -> tuple[int, dict[str, Any], float]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return resp.status, json.loads(raw), latency_ms
    except urllib.error.HTTPError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"error": raw}
        return exc.code, data, latency_ms
    except urllib.error.URLError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return 0, {"error": str(exc.reason)}, latency_ms
    except (TimeoutError, socket.timeout):
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return 0, {"error": "timeout"}, latency_ms


def probe_health(base_url: str) -> dict[str, Any]:
    status, raw, body = _get(base_url.rstrip("/") + "/health")
    return {"status_code": status, "body": body, "raw": raw[:500]}


def probe_metrics(base_url: str) -> dict[str, Any]:
    status, raw, body = _get(base_url.rstrip("/") + "/metrics", timeout=15.0)
    kv_gauges: dict[str, float] = {}
    if isinstance(raw, str):
        for line in raw.splitlines():
            if "kv_cache" in line.lower() and not line.startswith("#"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        kv_gauges[parts[0]] = float(parts[-1])
                    except ValueError:
                        pass
    return {
        "status_code": status,
        "kv_cache_gauges": kv_gauges,
        "has_kv_cache_tokens": any("kv_cache" in k.lower() for k in kv_gauges),
    }


def probe_slots(base_url: str) -> dict[str, Any]:
    status, raw, body = _get(base_url.rstrip("/") + "/slots")
    slots: list[dict[str, Any]] = []
    if isinstance(body, list):
        slots = [s for s in body if isinstance(s, dict)]
    elif isinstance(body, dict) and isinstance(body.get("slots"), list):
        slots = [s for s in body["slots"] if isinstance(s, dict)]
    return {
        "status_code": status,
        "slot_count": len(slots),
        "slots": [
            {
                "id": s.get("id", s.get("id_slot")),
                "n_token_total": s.get("n_token_total", s.get("n_tokens")),
                "is_processing": s.get("is_processing"),
            }
            for s in slots
        ],
    }


def probe_slot_save(base_url: str, id_slot: int = 0, filename: str = "kv-probe.bin") -> dict[str, Any]:
    query = urllib.parse.urlencode({"action": "save"})
    url = f"{base_url.rstrip('/')}/slots/{int(id_slot)}?{query}"
    status, body, latency_ms = _post_json(url, {"filename": filename}, timeout=30.0)
    return {
        "status_code": status,
        "body": body,
        "latency_ms": round(latency_ms, 3),
        "n_saved": body.get("n_saved") if isinstance(body, dict) else None,
    }


def _extract_turn(raw: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    usage = raw.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    timings = raw.get("timings") or {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    return {
        "id_slot": raw.get("id_slot"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": cached if isinstance(cached, int) else 0,
        "cache_n": timings.get("cache_n"),
        "prompt_n": timings.get("prompt_n"),
        "latency_ms": round(latency_ms, 3),
    }


def run_session_probe(
    base_url: str,
    *,
    sessions: int = 4,
    turns: int = 4,
    max_tokens: int = 32,
    tier: int = 0,
) -> dict[str, Any]:
    chat_url = base_url.rstrip("/") + "/v1/chat/completions"
    session_results: list[dict[str, Any]] = []
    errors: list[str] = []
    turn_cached: dict[int, list[int]] = {t: [] for t in range(1, 5)}
    slot_reuse_hits = 0
    slot_reuse_total = 0

    timeout_s = TIER_TIMEOUT_S.get(tier, 300.0)

    for sid in range(sessions):
        session_id = f"kv-audit-s{sid}"
        id_slot: int | None = sid  # bind physical slot from turn 0
        turns_data: list[dict[str, Any]] = []
        for turn in range(turns):
            messages = [
                {"role": "system", "content": LONG_STABLE_SYSTEM_PROMPT},
                {"role": "user", "content": f"session={session_id} turn={turn} short query"},
            ]
            payload: dict[str, Any] = {
                "messages": messages,
                "cache_prompt": True,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": False,
            }
            if id_slot is not None:
                payload["id_slot"] = id_slot
            if tier == 3:
                payload["chat_template_kwargs"] = {"enable_thinking": False}

            status, raw, latency_ms = _post_json(chat_url, payload, timeout=timeout_s)
            if status != 200 or not isinstance(raw, dict):
                errors.append(f"{session_id}:turn{turn}:HTTP {status}:{raw}")
                break
            turn_rec = _extract_turn(raw, latency_ms)
            turn_rec["turn"] = turn
            turns_data.append(turn_rec)
            turn_idx = turn + 1
            if turn_idx in turn_cached:
                turn_cached[turn_idx].append(int(turn_rec.get("cached_tokens") or 0))

            new_slot = turn_rec.get("id_slot")
            if turn > 0 and id_slot is not None and new_slot == id_slot:
                slot_reuse_hits += 1
            if turn > 0:
                slot_reuse_total += 1
            if isinstance(new_slot, int):
                id_slot = new_slot

        session_results.append({"session_id": session_id, "turns": turns_data})

    def _mean(vals: list[int]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    summary = {
        "turn1_cached_mean": _mean(turn_cached[1]),
        "turn2_cached_mean": _mean(turn_cached[2]) if turns >= 2 else None,
        "turn3_cached_mean": _mean(turn_cached[3]) if turns >= 3 else None,
        "turn4_cached_mean": _mean(turn_cached[4]) if turns >= 4 else None,
        "slot_reuse_rate": round(slot_reuse_hits / slot_reuse_total, 4) if slot_reuse_total else 0.0,
    }

    return {
        "base_url": base_url,
        "tier": tier,
        "sessions": sessions,
        "turns": turns,
        "health": probe_health(base_url),
        "metrics": probe_metrics(base_url),
        "slots_before": probe_slots(base_url),
        "sessions_detail": session_results,
        "summary": summary,
        "errors": errors,
        "slot_save": probe_slot_save(base_url, id_slot=0),
    }


def run_cross_tier_isolation(
    tier_urls: dict[int, str],
    *,
    turns: int = 2,
) -> dict[str, Any]:
    """Prove tier caches are isolated — each tier turn1 cold, turn2 warm."""
    results: dict[str, Any] = {}
    for tier, url in sorted(tier_urls.items()):
        chat_url = url.rstrip("/") + "/v1/chat/completions"
        session_id = f"escalation-tier{tier}"
        id_slot: int | None = None
        turns_data: list[dict[str, Any]] = []
        for turn in range(turns):
            messages = [
                {"role": "system", "content": LONG_STABLE_SYSTEM_PROMPT},
                {"role": "user", "content": ESCALATION_PROMPT if turn == 0 else f"{session_id} follow-up turn {turn}"},
            ]
            payload: dict[str, Any] = {
                "messages": messages,
                "cache_prompt": True,
                "max_tokens": 64,
                "temperature": 0.2,
                "stream": False,
            }
            if id_slot is not None:
                payload["id_slot"] = id_slot
            if tier == 3:
                payload["chat_template_kwargs"] = {"enable_thinking": False}
            timeout_s = TIER_TIMEOUT_S.get(tier, 300.0)
            status, raw, latency_ms = _post_json(chat_url, payload, timeout=timeout_s)
            if status != 200:
                turns_data.append({"turn": turn, "error": f"HTTP {status}", "body": raw})
                break
            rec = _extract_turn(raw, latency_ms)
            rec["turn"] = turn
            turns_data.append(rec)
            if isinstance(rec.get("id_slot"), int):
                id_slot = rec["id_slot"]
        results[f"tier{tier}"] = {
            "url": url,
            "turns": turns_data,
            "turn1_cached": turns_data[0].get("cached_tokens") if turns_data else None,
            "turn2_cached": turns_data[1].get("cached_tokens") if len(turns_data) > 1 else None,
        }
    return {"cross_tier_isolation": results, "escalation_prompt": ESCALATION_PROMPT}


def run_radix_gateway_probe(
    gateway_url: str,
    *,
    sessions: int = 4,
    turns: int = 4,
    max_tokens: int = 32,
) -> dict[str, Any]:
    """Exercise RadixSlotRouter via gateway DIPA path."""
    chat_url = gateway_url.rstrip("/") + "/v1/chat/completions"
    session_results: list[dict[str, Any]] = []
    max_radix_hits = 0.0
    errors: list[str] = []

    for sid in range(sessions):
        session_id = f"radix-s{sid}"
        turns_data: list[dict[str, Any]] = []
        for turn in range(turns):
            payload = {
                "session_id": session_id,
                "model": "cascade",
                "messages": [
                    {"role": "system", "content": LONG_STABLE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"session={session_id} turn={turn} short query"},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            }
            status, raw, latency_ms = _post_json(chat_url, payload, timeout=300.0)
            if status != 200 or not isinstance(raw, dict):
                errors.append(f"{session_id}:turn{turn}:HTTP {status}")
                break
            metrics = raw.get("metrics") or {}
            radix_hits = float(metrics.get("radix_prefix_hit_total") or 0)
            max_radix_hits = max(max_radix_hits, radix_hits)
            usage = raw.get("usage") or {}
            details = usage.get("prompt_tokens_details") or {}
            turns_data.append({
                "turn": turn,
                "tier_used": raw.get("tier_used"),
                "cached_tokens": details.get("cached_tokens") if isinstance(details, dict) else None,
                "radix_prefix_hit_total": radix_hits,
                "radix_match_len": metrics.get("radix_match_len"),
                "id_slot": metrics.get("id_slot") or metrics.get("slot_id"),
                "latency_ms": round(latency_ms, 3),
            })
        session_results.append({"session_id": session_id, "turns": turns_data})

    return {
        "gateway_url": gateway_url,
        "sessions": sessions,
        "turns": turns,
        "max_radix_prefix_hit_total": max_radix_hits,
        "radix_pass": max_radix_hits >= 1.0,
        "sessions_detail": session_results,
        "errors": errors,
    }


def build_summary_table(tier_results: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for tier in sorted(tier_results):
        s = tier_results[tier].get("summary") or {}
        rows.append({
            "tier": tier,
            "turn1_cached": s.get("turn1_cached_mean"),
            "turn2_cached": s.get("turn2_cached_mean"),
            "turn3_cached": s.get("turn3_cached_mean"),
            "turn4_cached": s.get("turn4_cached_mean"),
            "slot_reuse_rate": s.get("slot_reuse_rate"),
        })
    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-tier KV cache verification")
    parser.add_argument("--tier", choices=["1", "2", "3", "all"], default="all")
    parser.add_argument("--url", default="", help="Override base URL (single tier mode)")
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "evidence" / "latest")
    parser.add_argument("--radix-gateway", default="", help="Gateway URL for radix probe")
    parser.add_argument("--out", type=Path, default=None, help="Single output file")
    args = parser.parse_args()

    out_dir = args.out_dir
    tier_results: dict[int, dict[str, Any]] = {}

    tiers_to_run: list[int]
    if args.tier == "all":
        tiers_to_run = [1, 2, 3]
    else:
        tiers_to_run = [int(args.tier)]

    for tier in tiers_to_run:
        url = args.url or TIER_URLS[tier]
        print(f"Probing tier{tier} @ {url} ...", file=sys.stderr)
        try:
            result = run_session_probe(
                url,
                sessions=args.sessions,
                turns=args.turns,
                tier=tier,
            )
        except Exception as exc:  # noqa: BLE001
            result = {
                "base_url": url,
                "tier": tier,
                "errors": [f"probe_failed:{exc}"],
                "summary": {},
            }
        tier_results[tier] = result
        out_path = out_dir / f"kv-cache-tier{tier}.json"
        write_json(out_path, result)
        print(f"Wrote {out_path}", file=sys.stderr)

    if len(tier_results) > 1:
        cross = run_cross_tier_isolation(TIER_URLS, turns=2)
        cross_path = out_dir / "kv-cache-cross-tier.json"
        write_json(cross_path, cross)
        print(f"Wrote {cross_path}", file=sys.stderr)

    if args.radix_gateway:
        radix = run_radix_gateway_probe(args.radix_gateway, sessions=args.sessions, turns=args.turns)
        radix_path = args.out or (out_dir / "kv-cache-radix.json")
        write_json(radix_path, radix)
        print(f"Wrote {radix_path}", file=sys.stderr)

    aggregate = {
        "summary_table": build_summary_table(tier_results),
        "tiers": {str(k): v for k, v in tier_results.items()},
    }
    if len(tier_results) > 1:
        aggregate["cross_tier"] = json.loads(
            (out_dir / "kv-cache-cross-tier.json").read_text(encoding="utf-8")
        )
    agg_path = out_dir / "kv-cache-aggregate.json"
    write_json(agg_path, aggregate)
    print(json.dumps(aggregate["summary_table"], indent=2))


if __name__ == "__main__":
    main()
