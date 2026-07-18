#!/usr/bin/env python3
"""Probe llama-server for OpenAI logprobs / n_probs support."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def post(url: str, payload: dict) -> tuple[int, dict | str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, raw


def has_logits(payload: dict) -> bool:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return False
    c0 = choices[0]
    return bool(
        c0.get("logprobs")
        or c0.get("completion_probabilities")
        or c0.get("probs")
        or payload.get("probs")
    )


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8080")).rstrip(
        "/"
    )
    url = f"{base}/v1/chat/completions"
    variants = [
        ("logprobs+top_logprobs", {"logprobs": True, "top_logprobs": 3}),
        ("n_probs", {"n_probs": 3}),
        ("logprobs_bool", {"logprobs": True}),
    ]
    base_payload = {
        "model": "default",
        "messages": [{"role": "user", "content": "Say hi"}],
        "max_tokens": 4,
        "temperature": 0.0,
    }
    results = []
    for name, extra in variants:
        code, body = post(url, {**base_payload, **extra})
        ok = isinstance(body, dict) and has_logits(body)
        results.append(
            {
                "variant": name,
                "http": code,
                "logits": ok,
                "keys": list((body.get("choices") or [{}])[0].keys())
                if isinstance(body, dict) and body.get("choices")
                else str(body)[:120],
            }
        )
    print(json.dumps({"url": url, "results": results}, indent=2))
    return 0 if any(r["logits"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
