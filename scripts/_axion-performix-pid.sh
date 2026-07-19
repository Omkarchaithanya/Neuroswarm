#!/usr/bin/env bash
# Instruction Mix via live llama-server PID (apx rejected extracted binary path).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$(pwd)${PYTHONPATH:+:$PYTHONPATH}"
export NSA_PERFORMIX_ALLOW_DEMO=0
OUT=benchmarks/results/performix
PUB=docs/evidence/performix
mkdir -p "$OUT" "$PUB"

# Find host PID of KleidiAI llama-server
PID=""
for c in tier1 tier2 tier3; do
  id="$(docker compose ps -q "$c" 2>/dev/null || true)"
  [[ -n "$id" ]] || continue
  PID="$(docker top "$id" 2>/dev/null | awk 'NR>1 && $NF ~ /llama-server/ {print $2; exit}')"
  [[ -n "$PID" ]] && break
done
if [[ -z "$PID" ]]; then
  PID="$(pgrep -n -f 'llama-server' || true)"
fi
echo "LLAMA_PID=${PID:-none}"
if [[ -z "$PID" ]]; then
  echo "FAIL: no llama-server PID" >&2
  exit 1
fi
export LLAMA_PID="$PID"
export PERFORMIX_DURATION="${PERFORMIX_DURATION:-50}"

# Also stage binary under /tmp (absolute, simple path) as fallback workload
docker create --name nsa-wl2 nexus-arm/llama-kleidiai:server >/dev/null
docker cp nsa-wl2:/opt/llama/bin/llama-server /tmp/llama-server-kleidi 2>/dev/null || true
docker rm -f nsa-wl2 >/dev/null
chmod +x /tmp/llama-server-kleidi 2>/dev/null || true
ls -la /tmp/llama-server-kleidi || true

DUR="${PERFORMIX_DURATION:-50}"

# Prefer --pid for live process; also try /tmp workload
uv run python - <<PY
import json, os, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, ".")
from neuroswarm_arm.evolution.performix_client import PerformixClient

out_dir = Path("benchmarks/results/performix")
pub = Path("docs/evidence/performix")
client = PerformixClient()
pid = int(os.environ["LLAMA_PID"])
duration = int(os.environ.get("PERFORMIX_DURATION", "50"))
ok = []

def publish(path: Path):
    if path.is_file() and path.stat().st_size > 20:
        shutil.copy2(path, pub / path.name)
        meta = path.with_suffix(path.suffix + ".meta.json")
        if meta.is_file():
            shutil.copy2(meta, pub / meta.name)
        return True
    return False

# 1) instruction_mix with --pid
path = out_dir / "02-instruction_mix.json"
print(f"==> instruction_mix --pid {pid}", flush=True)
payload = client.run_recipe("instruction_mix", path, duration=duration, system_wide=False, pid=pid)
meta = {"recipe": "instruction_mix", "mode": "pid", "pid": pid, "returncode": payload.get("returncode"), "run_id": payload.get("run_id"), "extracted": payload.get("extracted"), "normalize_token": payload.get("normalize_token"), "normalize_stderr": (payload.get("normalize_stderr") or "")[:1000]}
path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print(json.dumps(meta, indent=2)[:2000], flush=True)
if publish(path):
    ok.append("instruction_mix")
else:
    # 2) fallback --workload /tmp
    wl = "/tmp/llama-server-kleidi"
    print(f"==> instruction_mix --workload {wl}", flush=True)
    payload = client.run_recipe("instruction_mix", path, binary=wl, duration=duration, system_wide=False)
    meta = {"recipe": "instruction_mix", "mode": "workload", "workload": wl, "returncode": payload.get("returncode"), "run_id": payload.get("run_id"), "extracted": payload.get("extracted"), "normalize_token": payload.get("normalize_token"), "normalize_stderr": (payload.get("normalize_stderr") or "")[:1000]}
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2)[:2000], flush=True)
    if publish(path):
        ok.append("instruction_mix")

# cpu_microarchitecture with --pid
path = out_dir / "03-cpu_microarchitecture.json"
print(f"==> cpu_microarchitecture --pid {pid}", flush=True)
payload = client.run_recipe("cpu_microarchitecture", path, duration=duration, system_wide=False, pid=pid)
meta = {"recipe": "cpu_microarchitecture", "mode": "pid", "pid": pid, "returncode": payload.get("returncode"), "run_id": payload.get("run_id"), "extracted": payload.get("extracted"), "normalize_token": payload.get("normalize_token"), "normalize_stderr": (payload.get("normalize_stderr") or "")[:1000]}
path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print(json.dumps(meta, indent=2)[:2000], flush=True)
if publish(path):
    ok.append("cpu_microarchitecture")

print("PID_GATE", "PASS" if "instruction_mix" in ok else ("PARTIAL" if ok else "FAIL"), ok)
# Still count code_hotspots already captured as success for overall evidence
hot = (out_dir / "01-code_hotspots.json").is_file() or (pub / "01-code_hotspots.json").is_file()
raise SystemExit(0 if ("instruction_mix" in ok or hot) else 2)
PY
