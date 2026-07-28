#!/usr/bin/env bash
# Probe guest NUMA topology truth (Axion C4A = single UMA / 1 node).
# Writes docs/evidence/latest/numa-status.json and a text companion.
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${OUT_DIR:-$PROJECT_ROOT/docs/evidence/latest}"
mkdir -p "$OUT_DIR"

echo "==> NUMA probe (lscpu / numactl / sysfs / Python)"
{
  echo "### lscpu (NUMA)"
  lscpu 2>/dev/null | grep -i numa || echo "lscpu: numa lines unavailable"
  echo
  echo "### numactl --hardware"
  if command -v numactl >/dev/null 2>&1; then
    numactl --hardware 2>/dev/null || true
  else
    echo "numactl not installed (optional: apt-get install -y numactl)"
  fi
  echo
  echo "### sysfs nodes"
  if [[ -d /sys/devices/system/node ]]; then
    ls -1 /sys/devices/system/node | grep -E '^node[0-9]+' || true
    for n in /sys/devices/system/node/node[0-9]*; do
      [[ -e "$n/cpulist" ]] || continue
      echo "$(basename "$n") cpulist=$(cat "$n/cpulist")"
    done
  else
    echo "sysfs NUMA path missing (non-Linux or container without node topology)"
  fi
  echo
  echo "### GCE machine-type"
  curl -s -H "Metadata-Flavor: Google" \
    --max-time 2 \
    http://metadata.google.internal/computeMetadata/v1/instance/machine-type \
    2>/dev/null || echo "metadata unavailable (not on GCE?)"
  echo
} | tee "$OUT_DIR/numa-probe.txt"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v uv >/dev/null 2>&1; then
    PYTHON_BIN="uv run python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$PROJECT_ROOT"
$PYTHON_BIN - <<'PY' > "$OUT_DIR/numa-status.json"
import json
import sys
from neuroswarm_arm.runtime.haoe.topology.numa_status import collect_numa_status

status = collect_numa_status()
# Fail closed if someone claims multi-node bind on single-node host incorrectly.
assert status.numa_nodes >= 1
if status.numa_nodes == 1:
    assert status.cross_numa_penalty_applicable is False
    assert status.policy == "single_uma"
    assert all(v is None for v in status.bind_planned.values())
print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
print(
    f"OK: numa_nodes={status.numa_nodes} policy={status.policy} "
    f"cross_numa={status.cross_numa_penalty_applicable}",
    file=sys.stderr,
)
PY

echo "==> wrote $OUT_DIR/numa-status.json and $OUT_DIR/numa-probe.txt"
