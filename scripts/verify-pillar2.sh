#!/usr/bin/env bash
# Autonomous Pillar 2 verification (local / CI).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export NSA_ROUTER_ALLOW_HASH="${NSA_ROUTER_ALLOW_HASH:-1}"
export NSA_ROUTER_EMBEDDING_BACKEND="${NSA_ROUTER_EMBEDDING_BACKEND:-hash}"
export NSA_ROUTER_MCPGA_HASH="${NSA_ROUTER_MCPGA_HASH:-1}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "==> pytest router suite"
python -m pytest tests/runtime/router/ -q --tb=line

echo "==> mcpga harness (>=40 tools, reduction)"
python benchmarks/router_mcpga.py

echo "==> catalog count"
python - <<'PY'
from pathlib import Path
from neuroswarm_arm.runtime.router.registry_loader import RegistryLoader
n = len(RegistryLoader().load_path(Path("templates/mcp-servers")))
assert n >= 40, n
print(f"catalog_tools={n}")
PY

echo "pillar2 autonomous OK"
