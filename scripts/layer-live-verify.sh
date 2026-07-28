#!/usr/bin/env bash
# Layer live verification pipeline (steps 1–13 upstream; step 14 MAKS dedup below).
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_ROOT"

echo "==> step 14: MAKS multi-agent dedup"
LAYER_VERIFY_DIR="${PROJECT_ROOT}/docs/evidence/latest/layer-verify"
mkdir -p "$LAYER_VERIFY_DIR"
WORK_OUT="${PROJECT_ROOT}/work/benchmarks/maks_multi_agent_dedup.json"
if command -v uv >/dev/null 2>&1; then
  uv run python benchmarks/maks_multi_agent_dedup_bench.py --out "$WORK_OUT" \
    || printf '{"status":"error"}\n' > "$WORK_OUT"
else
  python3 benchmarks/maks_multi_agent_dedup_bench.py --out "$WORK_OUT" \
    || printf '{"status":"error"}\n' > "$WORK_OUT"
fi
cp -f "$WORK_OUT" "$LAYER_VERIFY_DIR/14-maks-dedup.json"
