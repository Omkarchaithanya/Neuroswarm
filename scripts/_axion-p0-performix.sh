#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/*.sh performix_capture.sh 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"
export NSA_PERFORMIX_ALLOW_DEMO=0
export NSA_AROP_PERFORMIX=1
export PERFORMIX_DURATION="${PERFORMIX_DURATION:-45}"
mkdir -p docs/evidence/performix benchmarks/results/performix
echo "==> performix_capture"
bash performix_capture.sh
echo "PERFORMIX_EXIT=$?"
echo "==> list evidence"
find docs/evidence/performix benchmarks/results/performix -type f 2>/dev/null | head -40
python3 - <<'PY'
from pathlib import Path
import json
paths = list(Path("docs/evidence/performix").rglob("*.json")) + list(Path("benchmarks/results/performix").rglob("*.json"))
print("json_count", len(paths))
mix = [p for p in paths if "instruction_mix" in p.name or "instruction-mix" in p.name]
hot = [p for p in paths if "code_hotspots" in p.name or "hotspot" in p.name.lower()]
print("instruction_mix_files", [str(p) for p in mix[:5]])
print("hotspots_files", [str(p) for p in hot[:5]])
# also check snapshot
snap = Path("work/performix/snapshot.json")
if snap.is_file():
    d = json.loads(snap.read_text())
    print("snapshot", {"source": d.get("source"), "hotspots_n": len(d.get("hotspots") or [])})
ok = bool(mix) or (snap.is_file() and (json.loads(snap.read_text()).get("source") == "apx"))
print("PERFORMIX_GATE", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 2)
PY
