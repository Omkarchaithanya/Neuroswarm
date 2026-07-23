#!/usr/bin/env bash
# Collect perf counters for llama-server during a benchmark run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "${ROOT}/scripts/validate_kleidiai.py" \
  --url "${NSA_TIER2_URL:-http://127.0.0.1:8080}" \
  --require || exit 1

PID="${1:-}"
OUT="${2:-work/benchmarks/perf_stat.json}"
BENCHMARK_RUN_ID="${3:-$(date +%s)}"

if [[ -z "${PID}" ]]; then
  echo "usage: $0 <llama-server-pid> [output.json] [benchmark_run_id]" >&2
  exit 1
fi

mkdir -p "$(dirname "${OUT}")"

perf stat -p "${PID}" -e cycles,instructions,cache-references,cache-misses,branch-misses \
  sleep 5 2>"${OUT}.raw" || true

python - <<'PY' "${OUT}.raw" "${OUT}" "${BENCHMARK_RUN_ID}" "${PID}"
import json
import re
import sys

raw_path, out_path, run_id, pid = sys.argv[1:5]
text = open(raw_path, encoding="utf-8", errors="ignore").read()
metrics = {}
for line in text.splitlines():
    m = re.match(r"\s*([\d,]+)\s+(\S+)", line)
    if m:
        metrics[m.group(2)] = int(m.group(1).replace(",", ""))

payload = {
    "benchmark_run_id": run_id,
    "pid": int(pid),
    "metrics": metrics,
    "raw_excerpt": text[-2000:],
}
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
print(json.dumps(payload, indent=2))
PY
