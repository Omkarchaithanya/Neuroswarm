#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> listing"
ls -la docs/evidence/performix/ benchmarks/results/performix/ 2>/dev/null || true
echo "==> metas"
for f in benchmarks/results/performix/*.meta.json; do
  [ -f "$f" ] || continue
  echo "--- $f ---"
  cat "$f"
  echo
done
echo "==> try instruction_mix export debug"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$(pwd)"
PERFORMIX_DURATION=40 uv run python - <<'PY' || python3 - <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, ".")
from neuroswarm_arm.evolution.performix_client import PerformixClient
out = Path("benchmarks/results/performix/retry-instruction_mix.json")
client = PerformixClient()
payload = client.run_recipe("instruction_mix", out, duration=40, system_wide=True)
print(json.dumps({k: payload.get(k) for k in ("returncode","run_id","export_returncode","normalize_token","normalize_stderr","extracted","stderr")}, indent=2, default=str)[:4000])
print("out_exists", out.is_file(), "size", out.stat().st_size if out.is_file() else 0)
if out.is_file():
    import shutil
    pub = Path("docs/evidence/performix")
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, pub / out.name)
    print("PUBLISHED", pub / out.name)
PY
