#!/usr/bin/env bash
set -euo pipefail
cd /home/tejaswini2482_gmail_com/neuroswarm-arm
curl -sf -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"xyzzy do the thing somehow"}],"max_tokens":32}' \
  > work/evidence/router-wire/chat-lowconf2.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("work/evidence/router-wire/chat-lowconf2.json").read_text())
m=d.get("metrics") or {}
keys=["cascade_start_tier","cost_router_tier","tier_used","backend","model","tool_confidence","cost_router_reason"]
print({k:m.get(k) for k in keys})
print("top", d.get("tier_used"))
start=int(m.get("cascade_start_tier") or 0)
used=int(d.get("tier_used") or m.get("tier_used") or 0)
assert start >= 2, start
assert used >= 2, (used, "expected ASCR to honor cascade_start_tier>=2")
# Prefer matching start when start==3
if start == 3:
    assert used == 3, (used, "started at 3 but finished on", used)
print("PASS ascr respects start tier")
PY
