#!/usr/bin/env bash
# bpftrace eBPF capture against Kleidi llama-server (ggml/llama symbols or honest fallback).
# Usage: bash scripts/capture-ebpf-llamacpp.sh
# Env: PERF_PID / NSA_PERF_PID, EBPF_DURATION (default 15)
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
DURATION="${EBPF_DURATION:-${NSA_EBPF_DURATION:-15}}"
SUMMARY="${OUT_DIR}/ebpf-llamacpp-summary.json"
RAW="${OUT_DIR}/ebpf-llamacpp-${STAMP}.txt"
BT="${OUT_DIR}/ebpf-llamacpp-${STAMP}.bt"
LIBS_DIR="${OUT_DIR}/ebpf-libs-${STAMP}"

write_unavailable() {
  local reason="$1"
  python3 - "$SUMMARY" "$reason" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "source": "ebpf_unavailable",
  "reason": sys.argv[2],
  "operator_counts": {},
  "note": "ProfInfer is research-only; this path uses stock bpftrace as the open-source equivalent.",
}, indent=2), encoding="utf-8")
print(f"Wrote {sys.argv[1]} source=ebpf_unavailable reason={sys.argv[2]}")
PY
}

pick_llama_pid() {
  local pid
  pid="$(pgrep -af 'DeepSeek-R1|7B-Q4' | awk '/llama-server/{print $1; exit}' || true)"
  if [[ -z "${pid}" ]]; then
    pid="$(pgrep -af 'llama-server' | grep -v 'bash\|pgrep\|capture-ebpf' | awk '{print $1; exit}' || true)"
  fi
  echo "${pid:-}"
}

pick_tier3_cid() {
  docker ps --format '{{.ID}} {{.Names}}' 2>/dev/null | awk '/tier3/{print $1; exit}' || true
}

if ! command -v bpftrace >/dev/null 2>&1; then
  write_unavailable "bpftrace_missing"
  exit 1
fi

PID="${PERF_PID:-${NSA_PERF_PID:-}}"
if [[ -z "${PID}" ]]; then
  PID="$(pick_llama_pid)"
fi
if [[ -z "${PID}" ]] || ! ps -p "${PID}" >/dev/null 2>&1; then
  write_unavailable "no_llama_pid"
  exit 1
fi

EXE=""
# Container PIDs: path exists in the mount ns; avoid readlink -f (host path missing).
if command -v sudo >/dev/null 2>&1; then
  EXE="$(sudo -n readlink "/proc/${PID}/exe" 2>/dev/null || sudo readlink "/proc/${PID}/exe" 2>/dev/null || true)"
fi
if [[ -z "${EXE}" ]]; then
  EXE="$(readlink "/proc/${PID}/exe" 2>/dev/null || true)"
fi
# Prefer host-visible path via /proc/PID/root
if [[ -n "${EXE}" && -e "/proc/${PID}/root${EXE}" ]]; then
  EXE="/proc/${PID}/root${EXE}"
elif [[ -e "/proc/${PID}/root/opt/llama/bin/llama-server" ]]; then
  EXE="/proc/${PID}/root/opt/llama/bin/llama-server"
fi

CID="$(pick_tier3_cid)"
PROBE_TARGETS=()
mkdir -p "${LIBS_DIR}"

# Host path may be container-private (/opt/llama/...); materialize via docker cp.
if [[ -n "${CID}" ]]; then
  docker exec "${CID}" sh -c '
    mkdir -p /tmp/ns-ebpf-libs
    for n in llama-server libggml.so.0 libggml-cpu.so.0 libggml-base.so.0 libllama.so.0; do
      if [ -e /opt/llama/bin/$n ]; then cp -L /opt/llama/bin/$n /tmp/ns-ebpf-libs/$n
      elif [ -e /opt/llama/lib/$n ]; then cp -L /opt/llama/lib/$n /tmp/ns-ebpf-libs/$n
      fi
    done
  ' 2>/dev/null || true
  docker cp "${CID}:/tmp/ns-ebpf-libs/." "${LIBS_DIR}/" 2>/dev/null || true
fi

CANDIDATE_SYMS=(
  ggml_graph_compute
  ggml_backend_sched_graph_compute
  llama_decode
  llama_encode
  ggml_backend_cpu_graph_compute
)

# Map symbol -> binary path for uprobe attach (prefer libs that export the symbol).
declare -A SYM_BIN=()
FOUND_SYMS=()
scan_bin() {
  local bin="$1"
  [[ -f "${bin}" && -s "${bin}" ]] || return 0
  local list=""
  if command -v nm >/dev/null 2>&1; then
    list="$(nm -D "${bin}" 2>/dev/null | awk '{print $NF}'; nm "${bin}" 2>/dev/null | awk '{print $NF}')"
  fi
  if [[ -z "${list}" ]] && command -v readelf >/dev/null 2>&1; then
    list="$(readelf -Ws "${bin}" 2>/dev/null | awk '{print $NF}')"
  fi
  local s
  for s in "${CANDIDATE_SYMS[@]}"; do
    if echo "${list}" | grep -qx "${s}"; then
      if [[ -z "${SYM_BIN[$s]:-}" ]]; then
        SYM_BIN[$s]="${bin}"
        FOUND_SYMS+=("${s}")
      fi
    fi
  done
}

if [[ -n "${EXE}" && -r "${EXE}" ]]; then
  scan_bin "${EXE}"
fi
for f in "${LIBS_DIR}"/*; do
  [[ -f "${f}" ]] || continue
  scan_bin "${f}"
done

# Prefer container path for live uprobe attach when we know it.
ATTACH_EXE="${EXE}"
if [[ -n "${CID}" ]]; then
  # bpftrace uprobe needs a path visible in the target mount ns — use /proc/PID/root
  if [[ -e "/proc/${PID}/root/opt/llama/bin/llama-server" ]]; then
    ATTACH_EXE="/proc/${PID}/root/opt/llama/bin/llama-server"
  fi
fi

echo "PID=${PID} EXE=${EXE:-unknown} ATTACH=${ATTACH_EXE:-none} DURATION=${DURATION}s"
echo "symbols_found=${FOUND_SYMS[*]:-none}"

# Chat load aimed at profiled tier (direct :8083 for DeepSeek/tier3).
(
  for _ in $(seq 1 $((DURATION + 5))); do
    curl -sS -m 60 -X POST http://127.0.0.1:8083/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"default","messages":[{"role":"user","content":"Say hi."}],"max_tokens":12}' \
      >/dev/null 2>&1 || \
    curl -sS -m 60 -X POST http://127.0.0.1:8000/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"default","messages":[{"role":"user","content":"Say hi."}],"max_tokens":12}' \
      >/dev/null 2>&1 || true
    sleep 1
  done
) &
LOAD_PID=$!
sleep 1

MODE="uprobes"
if [[ ${#FOUND_SYMS[@]} -eq 0 ]]; then
  MODE="oncpu_fallback"
  cat >"${BT}" <<EOF
/* on-CPU samples for target PID (and llama-server comm fallback) */
profile:hz:99 /pid == ${PID}/ { @[ustack(5)] = count(); @hits = count(); }
profile:hz:99 /comm == "llama-server" && pid == ${PID}/ { @hits_comm = count(); }
interval:s:${DURATION} { exit(); }
EOF
else
  {
    echo "/* ggml / llama uprobes — NeuroSwarm open-source eBPF path (not ProfInfer) */"
    for s in "${FOUND_SYMS[@]}"; do
      bin="${SYM_BIN[$s]}"
      # Prefer live process root path for matching libs.
      base="$(basename "${bin}")"
      live="/proc/${PID}/root/opt/llama/lib/${base}"
      if [[ -e "${live}" ]]; then
        bin="${live}"
      elif [[ -e "/proc/${PID}/root/opt/llama/bin/${base}" ]]; then
        bin="/proc/${PID}/root/opt/llama/bin/${base}"
      fi
      echo "uprobe:${bin}:${s} { @hits[\"${s}\"] = count(); }"
      echo "uretprobe:${bin}:${s} { @ret[\"${s}\"] = count(); }"
    done
    echo "interval:s:${DURATION} { exit(); }"
  } >"${BT}"
fi

set +e
sudo -n bpftrace "${BT}" >"${RAW}" 2>&1
BT_RC=$?
if [[ ${BT_RC} -ne 0 ]]; then
  bpftrace "${BT}" >"${RAW}" 2>&1
  BT_RC=$?
fi
set -e
wait "${LOAD_PID}" 2>/dev/null || true

if [[ ${BT_RC} -ne 0 ]]; then
  reason="bpftrace_failed"
  if grep -qiE 'permission|CAP_BPF|Operation not permitted' "${RAW}" 2>/dev/null; then
    reason="cap_bpf_or_permission"
  elif grep -qiE 'could not resolve|no such file|symbol' "${RAW}" 2>/dev/null; then
    reason="symbol_or_attach_failed"
  fi
  # Still emit oncpu fallback attempt summary if raw has useful stacks
  if grep -qE '@\[' "${RAW}" 2>/dev/null; then
    MODE="partial"
  else
    write_unavailable "${reason}"
    echo "bpftrace log: ${RAW}"
    exit 1
  fi
fi

python3 - "$SUMMARY" "$PID" "${EXE:-}" "$MODE" "$DURATION" "$RAW" "${FOUND_SYMS[*]:-}" <<'PY'
import json, re, sys
from pathlib import Path

summary, pid, exe, mode, duration, raw_path, found = sys.argv[1:8]
text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
counts: dict[str, float] = {}
for m in re.finditer(r'@\w+\["([^"]+)"\]:\s*([\d]+)', text):
    counts[m.group(1)] = counts.get(m.group(1), 0.0) + float(m.group(2))
for m in re.finditer(r'@\w+\[([A-Za-z0-9_]+)\]:\s*([\d]+)', text):
    counts[m.group(1)] = counts.get(m.group(1), 0.0) + float(m.group(2))

stack_samples = len(re.findall(r'@\[', text))
hit_m = re.search(r'@hits:\s*([\d]+)', text)
hit_comm = re.search(r'@hits_comm:\s*([\d]+)', text)
if hit_m:
    counts["_oncpu_hits"] = float(hit_m.group(1))
if hit_comm:
    counts["_oncpu_hits_comm"] = float(hit_comm.group(1))
payload = {
    "source": "ebpf_bpftrace",
    "pid": int(pid),
    "exe": exe,
    "mode": mode,
    "duration_s": float(duration),
    "symbols_found": [s for s in found.split() if s],
    "operator_counts": counts,
    "stack_buckets": stack_samples,
    "raw": raw_path,
    "note": "Open-source bpftrace path; ProfInfer (arXiv:2601.20755) is research-only and not vendored.",
}
Path(summary).write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"Wrote {summary} source=ebpf_bpftrace mode={mode} ops={len(counts)} stacks={stack_samples}")
PY

echo "Done. Summary: ${SUMMARY}"
