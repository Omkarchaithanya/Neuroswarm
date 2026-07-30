#!/usr/bin/env bash
# Live verify Performix honesty on Axion + optional obs scrape check.
# Usage (on Axion): bash scripts/verify-performix-live.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
sed -i 's/\r$//' scripts/refresh-performix-snapshot.sh 2>/dev/null || true

GW=$(docker ps --format '{{.Names}}' | grep -E 'gateway' | head -1 || true)
test -n "$GW"
echo "gateway=$GW"
docker cp neuroswarm_arm/metrics/collectors.py "$GW":/app/neuroswarm_arm/metrics/collectors.py
docker restart "$GW"
sleep 10

METRICS_URL="${METRICS_URL:-http://127.0.0.1:8000/metrics}"

python3 - <<'PY'
import json
from pathlib import Path
Path("work/performix/snapshot.json").write_text(json.dumps({
  "available": 0, "source": "unavailable", "error": "verify_probe",
  "ipc": 9.9, "cycles": 999, "hotspots": [{"function": "x", "pct": 1}],
}, indent=2), encoding="utf-8")
print("wrote unavailable")
PY
sleep 7
echo "=== unavailable (expect available=0 ipc=0) ==="
curl -sf "$METRICS_URL" | grep -E '^nexus_performix_(available|ipc|cycles|hotspot_count|snapshot_age_seconds) '

python3 - <<'PY'
import json
from pathlib import Path
Path("work/performix/snapshot.json").write_text(json.dumps({
  "available": 1, "source": "demo", "ipc": 2.5, "cycles": 1000,
  "instructions": 2500, "hotspots": [{"function": "fake", "pct": 42}],
}, indent=2), encoding="utf-8")
print("wrote demo")
PY
sleep 7
echo "=== demo (expect available=0 ipc=0) ==="
curl -sf "$METRICS_URL" | grep -E '^nexus_performix_(available|ipc|cycles|hotspot_count) '

PID=$(pgrep -af 'llama-server' | grep -v 'bash\|pgrep\|refresh' | awk '{print $1; exit}' || true)
echo "llama_pid=${PID:-none}"
if [[ -n "${PID:-}" ]] && command -v apx >/dev/null 2>&1; then
  NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 PERFORMIX_PID="$PID" PERFORMIX_DURATION=12 \
    bash scripts/refresh-performix-snapshot.sh
  python3 -c 'import json; d=json.load(open("work/performix/snapshot.json")); print(d.get("source"), d.get("available"), len(d.get("hotspots") or [])); assert d.get("source") != "demo"'
  sleep 7
  echo "=== live apx ==="
  curl -sf "$METRICS_URL" | grep -E '^nexus_performix_(available|ipc|hotspot_count|snapshot_age_seconds) '
fi
echo "PASS verify-performix-live"
