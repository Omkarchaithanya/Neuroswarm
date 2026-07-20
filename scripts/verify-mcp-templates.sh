#!/usr/bin/env bash
# Verify all 6 MCP server templates have server.py + okf-metadata.yaml and import.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SERVERS=(browser github postgres s3 slack web-search)
FAIL=0

for s in "${SERVERS[@]}"; do
  base="templates/mcp-servers/$s"
  if [[ ! -f "$base/server.py" ]]; then
    echo "FAIL missing $base/server.py"; FAIL=1; continue
  fi
  if [[ ! -f "$base/okf-metadata.yaml" ]]; then
    echo "FAIL missing $base/okf-metadata.yaml"; FAIL=1; continue
  fi
  echo "OK $s (server.py + okf-metadata.yaml)"
done

if [[ ! -f templates/mcp-servers/_shared/server_base.py ]]; then
  echo "FAIL missing _shared/server_base.py"; FAIL=1
fi

# Syntax check
if command -v uv >/dev/null 2>&1; then
  for s in "${SERVERS[@]}"; do
    uv run python -m py_compile "templates/mcp-servers/$s/server.py" || FAIL=1
  done
else
  for s in "${SERVERS[@]}"; do
    python3 -m py_compile "templates/mcp-servers/$s/server.py" || FAIL=1
  done
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "MCP template verify FAILED"
  exit 1
fi
echo "PASS: 6 MCP templates present and compile"
