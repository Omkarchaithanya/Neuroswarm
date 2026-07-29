#!/usr/bin/env bash
# PID-scoped Linux perf capture against Kleidi llama-server (under chat load).
# Usage: bash scripts/capture-linux-perf.sh
# Env: PERF_PID, PERF_DURATION (default 20), NSA_PERF_DURATION
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work/profiling
if [[ ! -w work/profiling ]]; then
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R "$(id -u):$(id -g)" work/profiling 2>/dev/null || sudo chmod -R a+rwX work/profiling 2>/dev/null || true
  fi
fi
OUT_DIR="work/profiling"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DURATION="${PERF_DURATION:-${NSA_PERF_DURATION:-20}}"
SUMMARY="${OUT_DIR}/perf-summary.json"
STAT_TXT="${OUT_DIR}/perf-stat-${STAMP}.txt"
RECORD_DIR="${OUT_DIR}/perf-record-${STAMP}"
REPORT_TXT="${OUT_DIR}/perf-report-${STAMP}.txt"
SCRIPT_TXT="${OUT_DIR}/perf-script-${STAMP}.txt"

pick_llama_pid() {
  local pid
  pid="$(pgrep -af 'DeepSeek-R1|7B-Q4' | awk '/llama-server/{print $1; exit}' || true)"
  if [[ -z "${pid}" ]]; then
    pid="$(pgrep -af 'llama-server' | grep -v 'bash\|pgrep\|capture-linux' | awk '{print $1; exit}' || true)"
  fi
  echo "${pid:-}"
}

PERF_BIN="$(command -v perf || true)"
if [[ -z "${PERF_BIN}" ]]; then
  echo "perf not on PATH — run: bash scripts/install-host-profilers.sh" >&2
  python3 - "$SUMMARY" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "source": "linux_perf_unavailable",
  "error": "perf_missing",
  "events": {},
  "sve_events_used": [],
  "hardware_pmu_available": 0.0,
}, indent=2), encoding="utf-8")
print(f"Wrote {sys.argv[1]} source=linux_perf_unavailable")
PY
  exit 1
fi

PID="${PERF_PID:-${NSA_PERF_PID:-}}"
if [[ -z "${PID}" ]]; then
  PID="$(pick_llama_pid)"
fi
if [[ -z "${PID}" ]] || ! ps -p "${PID}" >/dev/null 2>&1; then
  echo "No live llama-server PID — refusing idle system-wide capture" >&2
  python3 - "$SUMMARY" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "source": "linux_perf_unavailable",
  "error": "no_llama_pid",
  "events": {},
  "sve_events_used": [],
  "hardware_pmu_available": 0.0,
}, indent=2), encoding="utf-8")
PY
  exit 1
fi

# Soften paranoid for this session if needed (sudo).
if [[ -r /proc/sys/kernel/perf_event_paranoid ]]; then
  cur="$(cat /proc/sys/kernel/perf_event_paranoid)"
  if [[ "${cur}" -gt 1 ]] && command -v sudo >/dev/null 2>&1; then
    sudo -n sysctl -w kernel.perf_event_paranoid=1 >/dev/null 2>&1 || true
  fi
fi

echo "PERF_PID=${PID} DURATION=${DURATION}s"
ps -p "${PID}" -o pid,cmd || true

# Prefer sudo for -p attach: perf often exits 0 with "<not supported>" when paranoid=4.
run_perf() {
  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo -n "${PERF_BIN}" "$@"
    return $?
  fi
  "${PERF_BIN}" "$@"
}

# Detect hardware PMU (Arm). Many GCP Axion images expose only software events.
HW_PMU=0
if ls /sys/bus/event_source/devices/armv8_pmuv3* >/dev/null 2>&1; then
  HW_PMU=1
fi
# Probe whether cycles actually counts (not "<not supported>").
PROBE_OUT="$(run_perf stat -e cycles -- sleep 0.2 2>&1 || true)"
if echo "${PROBE_OUT}" | grep -qE '[0-9].*cycles' && ! echo "${PROBE_OUT}" | grep -qi 'not supported'; then
  HW_PMU=1
else
  HW_PMU=0
fi
echo "hardware_pmu_available=${HW_PMU}"

SVE_USED=()
if [[ "${HW_PMU}" -eq 1 ]]; then
  mapfile -t CANDIDATES < <(
    "${PERF_BIN}" list 2>/dev/null | grep -oiE '[a-z0-9_./-]*(sve2?|i8mm|neon|ase_inst|sve_inst)[a-z0-9_./-]*' | sort -u | head -12 || true
  )
  EVENTS=(cycles instructions cache-misses cache-references branch-misses branch-instructions)
  for ev in "${CANDIDATES[@]:-}"; do
    [[ -z "${ev}" ]] && continue
    [[ "${ev}" == *":"* && "${ev}" != *"/"* ]] && continue
    if run_perf stat -e "${ev}" -- true >/dev/null 2>&1; then
      EVENTS+=("${ev}")
      SVE_USED+=("${ev}")
    fi
  done
else
  # Honest software fallback — still PID-scoped under load.
  EVENTS=(task-clock cpu-clock context-switches cpu-migrations page-faults)
fi
EVENT_CSV="$(IFS=,; echo "${EVENTS[*]}")"
echo "events=${EVENT_CSV}"
echo "sve_events_used=${SVE_USED[*]:-none}"

# Chat load aimed at the profiled PID's tier (prefer direct tier3 :8083).
(
  for _ in $(seq 1 $((DURATION + 5))); do
    curl -sS -m 60 -X POST http://127.0.0.1:8083/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"default","messages":[{"role":"user","content":"Say hi in three words."}],"max_tokens":16}' \
      >/dev/null 2>&1 || \
    curl -sS -m 60 -X POST http://127.0.0.1:8000/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"default","messages":[{"role":"user","content":"Say hi in three words."}],"max_tokens":16}' \
      >/dev/null 2>&1 || true
    sleep 1
  done
) &
LOAD_PID=$!
sleep 2

# perf stat
set +e
run_perf stat -j -e "${EVENT_CSV}" -p "${PID}" -- sleep "${DURATION}" \
  >"${STAT_TXT}.jsonl" 2>"${STAT_TXT}"
STAT_RC=$?
if [[ ! -s "${STAT_TXT}.jsonl" ]] || grep -qi 'not supported' "${STAT_TXT}" 2>/dev/null; then
  run_perf stat -e "${EVENT_CSV}" -p "${PID}" -- sleep "${DURATION}" \
    >"${STAT_TXT}" 2>&1
  STAT_RC=$?
fi
set -e

# perf record (cpu-clock works without HW PMU)
mkdir -p "${RECORD_DIR}"
RECORD_EVENT="cpu-clock"
if [[ "${HW_PMU}" -eq 1 ]]; then
  RECORD_EVENT="cycles"
fi
set +e
run_perf record -e "${RECORD_EVENT}" -g -o "${RECORD_DIR}/perf.data" -p "${PID}" -- sleep "${DURATION}" \
  >"${RECORD_DIR}/record.log" 2>&1
REC_RC=$?
if [[ -f "${RECORD_DIR}/perf.data" ]]; then
  run_perf report -i "${RECORD_DIR}/perf.data" --stdio >"${REPORT_TXT}" 2>&1 || true
  run_perf script -i "${RECORD_DIR}/perf.data" >"${SCRIPT_TXT}" 2>&1 || true
fi
set -e

wait "${LOAD_PID}" 2>/dev/null || true

python3 - "$SUMMARY" "${PID}" "${DURATION}" "${STAT_TXT}" "${STAT_TXT}.jsonl" "${REPORT_TXT}" "${EVENT_CSV}" "${SVE_USED[*]:-}" "${STAT_RC}" "${REC_RC}" "${HW_PMU}" <<'PY'
import json, re, sys
from pathlib import Path

summary_path, pid, duration, stat_txt, stat_jsonl, report_txt, event_csv, sve_csv, stat_rc, rec_rc, hw_pmu = sys.argv[1:12]
events: dict[str, float] = {}
jp = Path(stat_jsonl)
if jp.exists():
    for line in jp.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        name = str(o.get("event") or o.get("event_name") or "").strip()
        val = o.get("counter-value") or o.get("counter_value") or o.get("value")
        if not name or val is None:
            continue
        try:
            events[name] = float(str(val).replace(",", ""))
        except Exception:
            pass
text = Path(stat_txt).read_text(encoding="utf-8", errors="replace") if Path(stat_txt).exists() else ""
patterns = {
    "cycles": r"([\d,]+)\s+cycles",
    "instructions": r"([\d,]+)\s+instructions",
    "cache-misses": r"([\d,]+)\s+cache-misses",
    "cache-references": r"([\d,]+)\s+cache-references",
    "branch-misses": r"([\d,]+)\s+branch-misses",
    "branch-instructions": r"([\d,]+)\s+branch-instructions",
    "task-clock": r"([\d,.]+)\s+task-clock",
    "cpu-clock": r"([\d,.]+)\s+cpu-clock",
    "context-switches": r"([\d,]+)\s+context-switches",
    "cpu-migrations": r"([\d,]+)\s+cpu-migrations",
    "page-faults": r"([\d,]+)\s+page-faults",
}
for key, pat in patterns.items():
    if key in events:
        continue
    m = re.search(pat, text, re.I)
    if m:
        try:
            events[key] = float(m.group(1).replace(",", ""))
        except Exception:
            pass

cycles = float(events.get("cycles") or events.get("cpu-cycles") or 0.0)
instr = float(events.get("instructions") or 0.0)
ipc = (instr / cycles) if cycles > 0 else 0.0
sve_used = [x for x in sve_csv.split() if x]
hw = int(hw_pmu)
# Prefer non-zero software counters as proof of attach when HW PMU absent.
nonzero = sum(1 for v in events.values() if float(v) > 0)
payload = {
    "source": "linux_perf",
    "pid": int(pid),
    "duration_s": float(duration),
    "stat_rc": int(stat_rc),
    "record_rc": int(rec_rc),
    "events": events,
    "event_list": [e for e in event_csv.split(",") if e],
    "sve_events_used": sve_used,
    "sve_events_available": 1.0 if sve_used else 0.0,
    "hardware_pmu_available": float(hw),
    "event_mode": "hardware" if hw else "software",
    "ipc": ipc,
    "nonzero_event_count": nonzero,
    "artifacts": {
        "stat_txt": stat_txt,
        "stat_jsonl": stat_jsonl,
        "report_txt": report_txt,
    },
}
Path(summary_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(
    f"Wrote {summary_path} source=linux_perf mode={payload['event_mode']} "
    f"ipc={ipc:.4f} events={len(events)} nonzero={nonzero} sve={len(sve_used)} pmu={hw}"
)
PY

echo "Done. Summary: ${SUMMARY}"
