#!/usr/bin/env bash
# One-shot live Performix refresh on Axion host (no demo).
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/refresh-performix-snapshot.sh 2>/dev/null || true
set +e
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 PERFORMIX_DURATION="${PERFORMIX_DURATION:-60}" \
  bash scripts/refresh-performix-snapshot.sh
RC=$?
set -e
echo "refresh_rc=$RC"
python3 - <<'PY'
import json
from pathlib import Path
p = Path("work/performix/snapshot.json")
if not p.is_file():
    print("missing snapshot")
    raise SystemExit(1)
d = json.loads(p.read_text(encoding="utf-8"))
hs = d.get("hotspots") or []
print({
    "source": d.get("source"),
    "available": d.get("available"),
    "error": d.get("error"),
    "ipc": d.get("ipc"),
    "hotspots_n": len(hs),
    "hotspots_sample": hs[:3],
})
src = d.get("source")
if src == "apx" and hs:
    raise SystemExit(0)
print("NOT_YET source=%r hotspots=%d" % (src, len(hs)))
raise SystemExit(2)
PY
