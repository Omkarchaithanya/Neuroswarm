#!/usr/bin/env bash
# Capture real Arm Performix evidence via PerformixClient (correct apx flow).
# GA recipes: code_hotspots, cpu_microarchitecture, instruction_mix,
# memory_access, system_characterization (preview). NO system-utilization.
#
# Usage (on Axion with apx installed):
#   bash performix_capture.sh
#   COMPARE=1 bash performix_capture.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
find scripts -name '*.sh' -print0 2>/dev/null | xargs -0 -r sed -i 's/\r$//' || true

OUT_DIR="${OUT_DIR:-benchmarks/results/performix}"
PUB_DIR="${PUB_DIR:-docs/evidence/performix}"
COMPARE="${COMPARE:-0}"

mkdir -p "$OUT_DIR" "$PUB_DIR"

if ! command -v apx >/dev/null 2>&1; then
  echo "apx not on PATH — trying scripts/install-performix.sh"
  bash scripts/install-performix.sh || true
fi
if ! command -v apx >/dev/null 2>&1; then
  echo "FAIL: apx missing. Install Arm Performix, then re-run." >&2
  exit 1
fi

# instruction_mix tool needs a working python3 venv on the target.
if ! python3 -m venv /tmp/nsa-apx-venv-check >/dev/null 2>&1; then
  echo "WARN: python3-venv missing — instruction_mix will fail. Install: sudo apt-get install -y python3-venv" >&2
else
  rm -rf /tmp/nsa-apx-venv-check
fi

# Instruction Mix / CPU Microarch need a binary --workload (not --system-wide).
if [[ -z "${NSA_BENCH_BINARY:-}" ]]; then
  mkdir -p work/bin
  if docker image inspect nexus-arm/llama-kleidiai:server >/dev/null 2>&1; then
    cid="$(docker create nexus-arm/llama-kleidiai:server)"
    docker cp "$cid:/opt/llama/bin/llama-server" work/bin/llama-server-kleidi 2>/dev/null \
      || docker cp "$cid:/usr/local/bin/llama-server" work/bin/llama-server-kleidi 2>/dev/null \
      || true
    docker rm -f "$cid" >/dev/null
    chmod +x work/bin/llama-server-kleidi 2>/dev/null || true
    if [[ -x work/bin/llama-server-kleidi ]]; then
      export NSA_BENCH_BINARY="$(pwd)/work/bin/llama-server-kleidi"
      echo "NSA_BENCH_BINARY=$NSA_BENCH_BINARY"
    fi
  fi
fi

EXTRA=()
if [[ -n "${NSA_BENCH_BINARY:-}" ]]; then
  EXTRA+=(--binary "$NSA_BENCH_BINARY")
fi

if command -v uv >/dev/null 2>&1; then
  uv run python scripts/performix_capture_recipes.py --out-dir "$OUT_DIR" --pub-dir "$PUB_DIR" "${EXTRA[@]}"
else
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    python3 scripts/performix_capture_recipes.py --out-dir "$OUT_DIR" --pub-dir "$PUB_DIR" "${EXTRA[@]}"
fi

if [[ "$COMPARE" == "1" ]]; then
  {
    echo "# Performix stock vs KleidiAI"
    echo
    echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    echo "1. Deploy stock: \`NSA_LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server\` → capture to \`${OUT_DIR}/stock\`"
    echo "2. Deploy Kleidi: \`bash scripts/deploy-kleidiai-tiers.sh\` → capture to \`${OUT_DIR}\`"
    echo "3. Diff Instruction Mix + Code Hotspots JSON (SIMD/I8MM share should rise on Kleidi)."
    echo
    echo "## Artifacts in this directory"
    ls -1 "$OUT_DIR"/*.json 2>/dev/null || echo "(none yet)"
  } | tee "$OUT_DIR/COMPARISON.md"
  cp -f "$OUT_DIR/COMPARISON.md" "$PUB_DIR/" 2>/dev/null || true
fi

echo "Done. Artifacts: $OUT_DIR (published: $PUB_DIR)"
