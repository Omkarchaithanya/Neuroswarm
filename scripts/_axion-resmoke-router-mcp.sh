#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/neuroswarm-arm"
OUT=work/layer-verify
mkdir -p "$OUT"
sed -i 's/\r$//' scripts/verify-mcp-templates.sh scripts/layer-live-verify.sh
chmod +x scripts/verify-mcp-templates.sh
echo "==> router via uv"
if command -v uv >/dev/null 2>&1; then
  uv run python benchmarks/router_accuracy.py 2>&1 | tee "$OUT/06-router-accuracy.txt" | tail -50
elif [[ -x .venv/bin/python ]]; then
  .venv/bin/python benchmarks/router_accuracy.py 2>&1 | tee "$OUT/06-router-accuracy.txt" | tail -50
else
  echo "NO_UV_OR_VENV" | tee "$OUT/06-router-accuracy.txt"
fi
echo "==> mcp templates"
bash scripts/verify-mcp-templates.sh 2>&1 | tee "$OUT/07-mcp-templates.txt" | tail -40
echo RE_SMOKE_DONE