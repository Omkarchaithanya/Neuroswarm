#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("work/arop/performix/code-hotspots.json").read_text()) if Path("work/arop/performix/code-hotspots.json").is_file() else {}
print("source", d.get("source"), "n", len(d.get("hotspots") or []))
print("sample", json.dumps((d.get("hotspots") or [])[:5], indent=2))
snap = json.loads(Path("work/performix/snapshot.json").read_text()) if Path("work/performix/snapshot.json").is_file() else {}
print("snap", {k: snap.get(k) for k in ("source","available","ipc","pmu_available")})
print("snap hotspots", len(snap.get("hotspots") or []), (snap.get("hotspots") or [])[:3])
PY
bash scripts/smoke-product-gaps.sh http://127.0.0.1:8000 || true
