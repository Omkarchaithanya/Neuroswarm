#!/usr/bin/env python3
"""SpecBench-style ASCR accept-mode smoke after N chat calls.

Prints accept mode labels from /metrics (nexus_ascr_* and ascr_*).
Requires gateway with NSA_LLAMA_N_PROBS>0 for a true logits path; otherwise
labels interim text_agree / quality_cascade honestly.

Usage:
  python scripts/ascr-logits-smoke.py --base http://127.0.0.1:8000 --n 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request


def _get(url: str, timeout: float = 30.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _post_json(url: str, payload: dict, timeout: float = 120.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _metric(text: str, *names: str) -> float | None:
    # Match bare gauge or labeled series; take last sample across aliases.
    last: float | None = None
    for name in names:
        pat = re.compile(rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)\s*$", re.M)
        hits = pat.findall(text)
        if hits:
            try:
                last = float(hits[-1])
            except ValueError:
                continue
    return last


def main() -> int:
    ap = argparse.ArgumentParser(description="ASCR logits / accept-mode smoke")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--model", default="default")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    ok = 0
    chat_modes: list[str] = []
    chat_logits = False
    for i in range(args.n):
        try:
            resp = _post_json(
                f"{base}/v1/chat/completions",
                {
                    "model": args.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Smoke {i}: write a short paragraph about Arm CPUs "
                                "and speculative decoding acceptance."
                            ),
                        }
                    ],
                    "max_tokens": 48,
                    "temperature": 0.0,
                },
            )
            ok += 1
            m = dict(resp.get("metrics") or {})
            if float(m.get("logits_available") or 0) > 0:
                chat_logits = True
            mode = str(
                m.get("ascr_mode")
                or (resp.get("raw") or {}).get("ascr_mode")
                or ""
            )
            if mode:
                chat_modes.append(mode)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"chat[{i}] failed: {exc}", file=sys.stderr)

    try:
        metrics = _get(f"{base}/metrics")
    except Exception as exc:
        print(f"metrics fetch failed: {exc}", file=sys.stderr)
        return 2

    gain = _metric(metrics, "nexus_ascr_speculation_gain", "ascr_speculation_gain")
    agree = _metric(metrics, "nexus_ascr_text_agreement", "ascr_text_agreement")
    qc = _metric(metrics, "nexus_ascr_quality_cascade_total", "ascr_quality_cascade_total")
    accept = _metric(metrics, "nexus_ascr_acceptance_rate", "ascr_acceptance_rate")

    mode_hint = "unknown"
    logits_path = False
    if chat_logits or (gain is not None and gain > 0):
        mode_hint = "speculative_logits"
        logits_path = True
    elif chat_modes and any(m == "speculative" for m in chat_modes):
        mode_hint = "speculative"
        logits_path = True
    elif chat_modes and any(m == "text_agree" for m in chat_modes):
        mode_hint = "text_agree_interim"
    elif agree is not None and agree > 0:
        mode_hint = "text_agree_interim"
    elif qc is not None and qc > 0:
        mode_hint = "quality_cascade_interim"
    elif "ascr_" in metrics or "nexus_ascr_" in metrics:
        mode_hint = "ascr_present_interim"

    print(
        json.dumps(
            {
                "chats_ok": ok,
                "chats_n": args.n,
                "accept_mode": mode_hint,
                "chat_ascr_modes": chat_modes,
                "chat_logits_available": chat_logits,
                "ascr_speculation_gain": gain,
                "ascr_text_agreement": agree,
                "ascr_quality_cascade_total": qc,
                "ascr_acceptance_rate": accept,
                "logits_path": logits_path,
                "note": (
                    "Set NSA_LLAMA_N_PROBS=5 for logits accept; "
                    "otherwise expect *_interim (honest)."
                ),
            },
            indent=2,
        )
    )
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
