#!/usr/bin/env bash
# Capture instruction_mix + cpu_microarchitecture with --workload (required by apx).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$(pwd)${PYTHONPATH:+:$PYTHONPATH}"
export NSA_PERFORMIX_ALLOW_DEMO=0
OUT=benchmarks/results/performix
PUB=docs/evidence/performix
mkdir -p "$OUT" "$PUB" work/bin

WL="${NSA_BENCH_BINARY:-}"
if [[ -z "$WL" || ! -x "$WL" ]]; then
  echo "==> extracting llama-server from KleidiAI image for --workload"
  docker create --name nsa-wl-extract nexus-arm/llama-kleidiai:server >/dev/null
  docker cp nsa-wl-extract:/opt/llama/bin/llama-server work/bin/llama-server-kleidi || \
    docker cp nsa-wl-extract:/usr/local/bin/llama-server work/bin/llama-server-kleidi || true
  docker rm -f nsa-wl-extract >/dev/null
  chmod +x work/bin/llama-server-kleidi 2>/dev/null || true
  WL="$(pwd)/work/bin/llama-server-kleidi"
fi
if [[ ! -x "$WL" ]]; then
  echo "FAIL: no workload binary at $WL" >&2
  exit 1
fi
echo "WORKLOAD=$WL"
export NSA_BENCH_BINARY="$WL"

DUR="${PERFORMIX_DURATION:-45}"
uv run python - <<PY
import json, os, shutil, sys
from pathlib import Path
sys.path.insert(0, ".")
from neuroswarm_arm.evolution.performix_client import PerformixClient

out_dir = Path("benchmarks/results/performix")
pub = Path("docs/evidence/performix")
client = PerformixClient()
wl = os.environ["NSA_BENCH_BINARY"]
duration = int(os.environ.get("PERFORMIX_DURATION", "45"))
ok = []
for i, rid in enumerate(["instruction_mix", "cpu_microarchitecture"], start=2):
    path = out_dir / f"{i:02d}-{rid}.json"
    print(f"==> {rid} --workload {wl}", flush=True)
    payload = client.run_recipe(rid, path, binary=wl, duration=duration, system_wide=False)
    meta = {
        "recipe": rid,
        "returncode": payload.get("returncode"),
        "run_id": payload.get("run_id"),
        "extracted": payload.get("extracted"),
        "normalize_token": payload.get("normalize_token"),
        "normalize_stderr": (payload.get("normalize_stderr") or "")[:800],
        "workload": wl,
    }
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2)[:1500], flush=True)
    if path.is_file() and path.stat().st_size > 20:
        shutil.copy2(path, pub / path.name)
        shutil.copy2(path.with_suffix(path.suffix + ".meta.json"), pub / (path.name + ".meta.json"))
        ok.append(rid)
        print(f"OK {rid}", flush=True)
    else:
        print(f"FAIL {rid}", flush=True)

print("WORKLOAD_GATE", "PASS" if "instruction_mix" in ok else "FAIL", ok)
raise SystemExit(0 if "instruction_mix" in ok else 2)
PY
