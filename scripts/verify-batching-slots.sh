#!/usr/bin/env bash
# Verify llama-server slot pool matches batching config (post-deploy gate).
# Usage: bash scripts/verify-batching-slots.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export TIER1_EXPECT="${NSA_LLAMA_N_PARALLEL:-8}"
export TIER2_EXPECT="${NSA_LLAMA_N_PARALLEL:-8}"
export TIER3_EXPECT="${TIER3_PARALLEL:-4}"

python3 <<'PY'
from __future__ import annotations

import json
import os
import urllib.request

EXPECT = {
    "tier1": (8081, int(os.environ.get("TIER1_EXPECT", "8"))),
    "tier2": (8082, int(os.environ.get("TIER2_EXPECT", "8"))),
    "tier3": (8083, int(os.environ.get("TIER3_EXPECT", "4"))),
}


def fetch_json(url: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return json.load(resp)
    except Exception:
        return None


def slot_summary(port: int) -> dict:
    slots_data = fetch_json(f"http://127.0.0.1:{port}/slots")
    props = fetch_json(f"http://127.0.0.1:{port}/props")
    if isinstance(slots_data, list):
        slots = [s for s in slots_data if isinstance(s, dict)]
    elif isinstance(slots_data, dict):
        slots = [s for s in slots_data.get("slots") or [] if isinstance(s, dict)]
    else:
        slots = []

    total_from_props = 0
    if isinstance(props, dict):
        for key in ("total_slots", "slot_n", "n_parallel", "parallel"):
            val = props.get(key)
            if isinstance(val, int) and val > 0:
                total_from_props = val
                break

    slot_count = max(len(slots), total_from_props)
    return {
        "ok": slots_data is not None or props is not None,
        "slot_count": slot_count,
        "slots_list_len": len(slots),
        "total_slots_props": total_from_props,
        "ids": [s.get("id") for s in slots],
        "n_ctx_values": [s.get("n_ctx") for s in slots if isinstance(s, dict)],
    }


fail = False
for name, (port, expect) in EXPECT.items():
    summary = slot_summary(port)
    count = int(summary.get("slot_count") or 0)
    print(f"==> {name} :{port} slots={count} (expect >= {expect}) {json.dumps(summary)}")
    if count < expect:
        print(f"FAIL {name}: expected >= {expect} slots, got {count}", flush=True)
        fail = True

if fail:
    raise SystemExit(1)

print("PASS: batching slot pools OK")
PY
