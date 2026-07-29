#!/usr/bin/env bash
# Install Linux perf + bpftrace on Axion (Neoverse) for open-source PMU / eBPF profiling.
# Usage: bash scripts/install-host-profilers.sh
set -euo pipefail

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E bash "$0" "$@"
    fi
    echo "error: run as root (or with sudo)" >&2
    exit 1
  fi
}

need_root "$@"
export DEBIAN_FRONTEND=noninteractive

KREL="$(uname -r)"
apt-get update -qq
apt-get install -y --no-install-recommends \
  linux-tools-common \
  "linux-tools-${KREL}" \
  bpftrace \
  binutils \
  elfutils \
  || apt-get install -y --no-install-recommends linux-tools-generic bpftrace binutils || true

# Some GCP images ship tools under /usr/lib/linux-tools-$KREL/perf
if ! command -v perf >/dev/null 2>&1; then
  for cand in "/usr/lib/linux-tools-${KREL}/perf" /usr/lib/linux-tools/*/perf; do
    if [[ -x "$cand" ]]; then
      ln -sfn "$cand" /usr/local/bin/perf
      break
    fi
  done
fi

echo
echo "=== NeuroSwarm host profilers ==="
echo "kernel: ${KREL}"
echo "perf: $(command -v perf || echo MISSING)"
echo "bpftrace: $(command -v bpftrace || echo MISSING)"
if [[ -r /proc/sys/kernel/perf_event_paranoid ]]; then
  echo "perf_event_paranoid: $(cat /proc/sys/kernel/perf_event_paranoid)"
  # GCP default is often 4 (blocks PMU for unprivileged). Soften for host profiling.
  if [[ "$(cat /proc/sys/kernel/perf_event_paranoid)" -gt 1 ]]; then
    sysctl -w kernel.perf_event_paranoid=1 >/dev/null || true
    echo "perf_event_paranoid (adjusted): $(cat /proc/sys/kernel/perf_event_paranoid)"
    echo "To persist: echo 'kernel.perf_event_paranoid=1' | tee /etc/sysctl.d/99-neuroswarm-perf.conf && sysctl --system"
  fi
fi
echo
echo "=== Arm / SIMD-ish PMU events (sample) ==="
if command -v perf >/dev/null 2>&1; then
  perf list 2>/dev/null | grep -iE '\bsve|sve2|neon|i8mm|armv8_pmu|ase_inst|sve_inst' | head -40 || echo "(none listed or needs sudo)"
  echo
  perf version 2>&1 | head -3 || true
else
  echo "perf not installed — install linux-tools for this kernel"
fi
echo
echo "Next:"
echo "  bash scripts/capture-linux-perf.sh"
echo "  bash scripts/capture-ebpf-llamacpp.sh"
echo "Docs: docs/profiling/linux-perf-ebpf.md"
