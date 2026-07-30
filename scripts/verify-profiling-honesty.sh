#!/usr/bin/env bash
# Verify llama-native + open-source profiling produce live data (never demo/fake).
# Usage (on Axion): bash scripts/verify-profiling-honesty.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work/profiling

echo "=== refuse demo/synthetic artifacts ==="
python3 - <<'PY'
import json
from pathlib import Path
bad = []
for root in (Path("work/profiling"), Path("work/performix")):
    if not root.exists():
        continue
    for p in root.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        src = str(d.get("source") or "").lower()
        if src in {"demo", "synthetic"} or src.startswith("demo"):
            bad.append((str(p), src))
if bad:
    raise SystemExit(f"FAIL demo artifacts present: {bad}")
print("OK no demo/synthetic sources")
PY

echo "=== llama timings (live) ==="
TIER="${TIER:-3}" MAX_TOKENS="${MAX_TOKENS:-32}" MODE=api bash scripts/capture-llama-timings.sh
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("work/profiling/llama-timings-summary.json").read_text())
assert d.get("source") == "llama_server_timings", d.get("source")
assert float(d.get("predicted_per_second") or 0) > 0
assert float(d.get("prompt_per_second") or 0) > 0
api = d.get("api") or {}
assert float((api.get("timings") or {}).get("predicted_per_second") or 0) == float(d["predicted_per_second"])
print("PASS timings", d["predicted_per_second"], d["prompt_per_second"])
PY

echo "=== llama-bench (live) ==="
TIER="${BENCH_TIER:-1}" THREADS=2 PROMPTS=64 NGEN=32 REPS=1 bash scripts/run-llama-bench-sweep.sh
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("work/profiling/llama-bench-summary.json").read_text())
assert d.get("source") == "llama_bench", d.get("source")
rows = d.get("rows") or []
assert rows and all(float(r.get("avg_ts") or 0) > 0 for r in rows)
print("PASS bench rows", len(rows))
PY

echo "=== tier /metrics (live) ==="
curl -sS -m 5 "http://127.0.0.1:808${TIER:-3}/metrics" | python3 - <<'PY'
import sys
text = sys.stdin.read()
assert "llamacpp:tokens_predicted_total" in text
val = None
for line in text.splitlines():
    if line.startswith("llamacpp:predicted_tokens_seconds "):
        val = float(line.split()[-1])
        break
assert val is not None and val > 0, val
print("PASS /metrics predicted_tokens_seconds", val)
PY

echo "=== linux perf (honest software fallback allowed) ==="
LLAMA_PID="$(pgrep -af 'DeepSeek-R1|7B-Q4' | awk '/llama-server/{print $1; exit}' || true)"
if [[ -z "${LLAMA_PID}" ]]; then
  LLAMA_PID="$(pgrep -af llama-server | grep -v 'bash\|pgrep' | awk '{print $1; exit}' || true)"
fi
export NSA_PERF_PID="${LLAMA_PID}" PERF_PID="${LLAMA_PID}"
PERF_DURATION="${PERF_DURATION:-5}" bash scripts/capture-linux-perf.sh
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("work/profiling/perf-summary.json").read_text())
assert d.get("source") == "linux_perf", d.get("source")
assert int(d.get("nonzero_event_count") or 0) > 0
if float(d.get("hardware_pmu_available") or 0) == 0:
    assert d.get("event_mode") == "software"
    assert float(d.get("ipc") or 0) == 0.0
print("PASS perf", d.get("event_mode"), "nonzero", d.get("nonzero_event_count"))
PY

echo "=== ebpf (live or honest unavailable) ==="
EBPF_DURATION="${EBPF_DURATION:-5}" bash scripts/capture-ebpf-llamacpp.sh || true
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("work/profiling/ebpf-llamacpp-summary.json").read_text())
src = d.get("source")
assert src in {"ebpf_bpftrace", "ebpf_unavailable"}, src
if src == "ebpf_bpftrace":
    ops = d.get("operator_counts") or {}
    hits = float(ops.get("_oncpu_hits") or ops.get("_oncpu_hits_comm") or 0)
    assert hits > 0 or int(d.get("stack_buckets") or 0) > 0
    print("PASS ebpf", d.get("mode"), "hits", hits)
else:
    assert d.get("reason")
    print("PASS ebpf unavailable", d.get("reason"))
PY

echo "ALL PROFILING HONESTY CHECKS PASSED"
