#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/tejaswini2482_gmail_com/neuroswarm-arm
cd "$ROOT"
GW=$(docker ps --format '{{.Names}}' | grep gateway | head -1)
docker cp neuroswarm_arm/runtime/armcascade/engine.py "$GW:/app/neuroswarm_arm/runtime/armcascade/engine.py"
docker cp neuroswarm_arm/runtime/armcascade/escalation/engine.py "$GW:/app/neuroswarm_arm/runtime/armcascade/escalation/engine.py"
docker exec "$GW" find /app/neuroswarm_arm/runtime/armcascade -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
docker restart "$GW"
sleep 15
Q="xyzzy debug $(date +%s) vague request"
curl -sf -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"$Q\"}],\"max_tokens\":32}" \
  > work/evidence/router-wire/chat-lowconf4.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("work/evidence/router-wire/chat-lowconf4.json").read_text())
m=d.get("metrics") or {}
print({k:m.get(k) for k in [
  "cascade_start_tier","ascr_planned_start_tier","ascr_start_tier","cost_router_tier",
  "tier_used","backend","escalated","ascr_mode"]})
print("top", d.get("tier_used"))
start=int(float(m.get("ascr_start_tier") or 0))
used=int(float(d.get("tier_used") or m.get("tier_used") or 0))
assert start == 3, start
assert used == 3, used
print("PASS ascr start=tier3 used=tier3")
PY
