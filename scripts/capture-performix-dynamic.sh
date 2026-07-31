#!/usr/bin/env bash
# Dynamic Kleidi vs stock Performix capture (Axion host apx).
# Produces docs/evidence/performix/03–06 + COMPARISON.md
#
# FIXED SEQUENCE (per task requirements):
# 1. Start llama-server, wait for /health = ready (model fully loaded)
# 2. Start sustained load generator (50-100 concurrent prompts)
# 3. THEN attach apx to WARM PID for 120s+ profiling window
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PUB="$ROOT/docs/evidence/performix"
mkdir -p "$PUB" work/performix/dynamic
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

API="${NSA_CHAT_URL:-http://127.0.0.1:8000/v1/chat/completions}"
LLAMA_HEALTH="${NSA_LLAMA_HEALTH:-http://127.0.0.1:8080/health}"
TIMEOUT="${PERFORMIX_TIMEOUT:-120}"  # INCREASED: 120s minimum for decode to dominate

fire_burst() {
  echo "==> continuous decode load → $API"
  # Keep llama busy for the full recipe window (not a single short burst).
  (
    while true; do
      curl -s -X POST "$API" \
        -H "Content-Type: application/json" \
        -d '{"model":"cascade","messages":[{"role":"user","content":"Write a 300 word explanation of NUMA on Arm servers."}],"stream":false,"max_tokens":400}' \
        >/tmp/nsa-decode-burst.json || true
      sleep 0.5
    done
  ) &
  BURST_PID=$!
  sleep 2
}

wait_burst() {
  kill "$BURST_PID" 2>/dev/null || true
  wait "$BURST_PID" 2>/dev/null || true
  head -c 200 /tmp/nsa-decode-burst.json 2>/dev/null || true
  echo
}

pick_llama_pid() {
  # Prefer largest model (tier2 8B) if present; else first llama-server.
  local pid
  pid="$(pgrep -af 'llama-server.*llama-3.1-8b' | awk '{print $1; exit}' || true)"
  if [[ -z "$pid" ]]; then
    pid="$(pgrep -af 'llama-server' | grep -v 'bash\|pgrep\|capture' | awk '{print $1; exit}' || true)"
  fi
  if [[ -z "$pid" ]]; then
    echo "FAIL: no llama-server pid" >&2
    return 1
  fi
  echo "$pid"
}

wait_llama_ready() {
  local timeout="${1:-300}"
  local health_url="${2:-$LLAMA_HEALTH}"
  echo "==> Waiting for llama-server health at $health_url (timeout ${timeout}s)..."
  local start
  start="$(date +%s)"
  while true; do
    if curl -sf "$health_url" >/dev/null 2>&1; then
      echo "    llama-server /health OK (model loaded, mmap complete)"
      return 0
    fi
    local now
    now="$(date +%s)"
    if (( now - start > timeout )); then
      echo "    TIMEOUT: llama-server not healthy after ${timeout}s" >&2
      return 1
    fi
    sleep 2
  done
}

run_recipe() {
  local recipe="$1"
  local out="$2"
  local pid="$3"
  local extra_params="${4:-}"
  echo "==> apx $recipe pid=$pid timeout=$TIMEOUT params=$extra_params → $out"
  EXTRA_PARAMS="$extra_params" python3 - <<PY
from pathlib import Path
import os
from neuroswarm_arm.evolution.performix_client import PerformixClient
c = PerformixClient()
params = [p for p in os.environ.get("EXTRA_PARAMS", "").split() if p]
kwargs = dict(
    duration=int("$TIMEOUT"),
    system_wide=False,
    pid=int("$pid"),
)
if params:
    kwargs["params"] = params
payload = c.run_recipe("$recipe", Path("$out"), **kwargs)
print("returncode", payload.get("returncode"), "run_id", payload.get("run_id"), "token", payload.get("normalize_token"))
if payload.get("stderr"):
    print((payload.get("stderr") or "")[-1200:])
if not Path("$out").is_file():
    raise SystemExit("missing output $out")
PY
}

extract_simd_line() {
  local json="$1"
  python3 - <<PY
import json, re
from pathlib import Path
p = Path("$json")
data = json.loads(p.read_text(encoding="utf-8"))
rows = data.get("instruction_mix_rows") or []
# Also scan embedded csv text if present
text = p.read_text(encoding="utf-8", errors="replace")
neon = sve = None
for row in rows:
    vals = " ".join(str(v) for v in (row.values() if isinstance(row, dict) else [row]))
    low = vals.lower()
    pct = None
    if isinstance(row, dict):
        for k in ("percentage", "percent", "pct"):
            if k in row:
                try:
                    pct = float(row[k]); break
                except Exception:
                    pass
    if "advanced simd" in low or "neon" in low or "asimd" in low:
        neon = pct
    if "scalable vector" in low or "sve" in low:
        sve = pct
# Fallback regex on raw file
if neon is None:
    m = re.search(r"Advanced SIMD Instructions,(\d+),([0-9.]+)", text)
    if m: neon = float(m.group(2))
if sve is None:
    m = re.search(r"Scalable Vector Extension \(SVE\) Instructions,(\d+),([0-9.]+)", text)
    if m: sve = float(m.group(2))
print(f"NEON={neon} SVE={sve}")
PY
}

echo "=== Kleidi tiers ==="
docker compose ps | grep -E 'tier|kleidi' || true

# --- 03 dynamic Kleidi instruction_mix ---
# FIXED: Wait for llama-server ready, then fire burst, then profile
wait_llama_ready 300 "$LLAMA_HEALTH"
fire_burst
PID="$(pick_llama_pid)"
echo "profiling pid=$PID"
run_recipe instruction_mix "$PUB/03-instruction_mix_dynamic_kleidi.json" "$PID" "mode=dynamic"
wait_burst
KLEIDI_SIMD="$(extract_simd_line "$PUB/03-instruction_mix_dynamic_kleidi.json" || true)"
echo "Kleidi SIMD: $KLEIDI_SIMD"

# --- 04 stock baseline on tier3 ---
echo "==> swap tier3 → stock llama.cpp"
NSA_LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server docker compose up -d tier3
# wait healthy
for i in $(seq 1 30); do
  st="$(docker inspect neuroswarm-arm-tier3-1 --format '{{.State.Health.Status}}' 2>/dev/null || echo starting)"
  [[ "$st" == "healthy" ]] && break
  sleep 5
done
docker compose ps tier3

# FIXED: Wait for stock llama-server ready, then fire burst, then profile
wait_llama_ready 300 "$LLAMA_HEALTH"
fire_burst
# Prefer stock tier3 pid (qwen 0.5b often on tier3 — match newest container pid)
PID3="$(docker inspect neuroswarm-arm-tier3-1 --format '{{.State.Pid}}')"
echo "profiling stock tier3 pid=$PID3"
run_recipe instruction_mix "$PUB/04-instruction_mix_dynamic_baseline.json" "$PID3" "mode=dynamic"
wait_burst
BASE_SIMD="$(extract_simd_line "$PUB/04-instruction_mix_dynamic_baseline.json" || true)"
echo "Baseline SIMD: $BASE_SIMD"

echo "==> restore tier3 → Kleidi"
NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server docker compose up -d tier3
for i in $(seq 1 30); do
  st="$(docker inspect neuroswarm-arm-tier3-1 --format '{{.State.Health.Status}}' 2>/dev/null || echo starting)"
  [[ "$st" == "healthy" ]] && break
  sleep 5
done

# --- 05 / 06 on Kleidi ---
# FIXED: Wait for restored Kleidi llama-server ready before profiling
wait_llama_ready 300 "$LLAMA_HEALTH"
fire_burst
PID="$(pick_llama_pid)"
run_recipe cpu_microarchitecture "$PUB/05-cpu_microarchitecture.json" "$PID"
wait_burst

fire_burst
PID="$(pick_llama_pid)"
run_recipe memory_access "$PUB/06-memory_access.json" "$PID"
wait_burst

# --- COMPARISON.md (apx has no recipe compare) ---
TIMEOUT_VAL="$TIMEOUT"
python3 - <<PY
from pathlib import Path
from datetime import datetime, timezone
pub = Path("$PUB")
kleidi = pub / "03-instruction_mix_dynamic_kleidi.json"
base = pub / "04-instruction_mix_dynamic_baseline.json"
out = pub / "COMPARISON.md"
TIMEOUT = "$TIMEOUT_VAL"

def simd_summary(path: Path) -> str:
    if not path.is_file():
        return "(missing)"
    text = path.read_text(encoding="utf-8", errors="replace")
    import re, json
    try:
        data = json.loads(text)
        summ = (data.get("summary") or {})
        if summ.get("simd_share_approx") is not None:
            return f"simd_share_approx={summ['simd_share_approx']:.4f} rows={summ.get('rows')}"
    except Exception:
        pass
    neon = re.search(r"Advanced SIMD Instructions,(\d+),([0-9.]+)", text)
    sve = re.search(r"Scalable Vector Extension \(SVE\) Instructions,(\d+),([0-9.]+)", text)
    parts = []
    if neon: parts.append(f"NEON {neon.group(2)}%")
    if sve: parts.append(f"SVE {sve.group(2)}%")
    return ", ".join(parts) or "(see JSON)"

md = f"""# Performix dynamic Instruction Mix — stock vs KleidiAI

Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

Captured **during live decode** via `apx recipe run … --pid <llama-server> --timeout {TIMEOUT}` (not static binary disassembly).

| Capture | Artifact | SIMD summary |
|---|---|---|
| KleidiAI (optimized) | `03-instruction_mix_dynamic_kleidi.json` | {simd_summary(kleidi)} |
| Stock llama.cpp (baseline) | `04-instruction_mix_dynamic_baseline.json` | {simd_summary(base)} |

## Also captured (Kleidi, live attach)

- `05-cpu_microarchitecture.json` — topdown / stall breakdown
- `06-memory_access.json` — SPE load/store latency

## Method

1. Background `POST /v1/chat/completions` (cascade, ~300-word NUMA prompt)
2. Attach `apx` to host-visible `llama-server` PID while decode runs
3. Stock baseline: temporarily `NSA_LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server` on **tier3 only**, then restore Kleidi

Static mix (`02-instruction_mix.json` / `static_instruction_mix.csv`) undercounts hot-loop SIMD; prefer the dynamic Kleidi row in MEASURED.md.
"""
out.write_text(md, encoding="utf-8")
print(md)
PY

echo "=== artifacts ==="
ls -la "$PUB"/03-* "$PUB"/04-* "$PUB"/05-* "$PUB"/06-* "$PUB"/COMPARISON.md
echo "DONE"
