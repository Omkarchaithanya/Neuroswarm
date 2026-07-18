#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/refresh-performix-snapshot.sh 2>/dev/null || true
echo "==> apx.err tail"
tail -40 work/performix/apx.err 2>/dev/null || true
echo "==> refresh duration=60"
set +e
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 PERFORMIX_DURATION=60 bash scripts/refresh-performix-snapshot.sh
echo "refresh_rc=$?"
set -e
python3 - <<'PY'
import json
from pathlib import Path
p = Path("work/performix/snapshot.json")
print(json.loads(p.read_text()) if p.is_file() else "missing")
PY
