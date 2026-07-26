#!/usr/bin/env bash
# Verify MCP server templates have server.py + ≥1 tool schema (*.tool.yaml).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/templates/mcp-servers"
FAIL=0
COUNT=0
for s in browser github postgres s3 slack web-search; do
  base="$BASE/$s"
  if [[ ! -f "$base/server.py" ]]; then
    echo "FAIL missing $base/server.py"; FAIL=1; continue
  fi
  n=$(find "$base" -name '*.tool.yaml' 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${n:-0}" -lt 1 ]]; then
    echo "FAIL $s has no *.tool.yaml schemas"; FAIL=1; continue
  fi
  COUNT=$((COUNT + n))
  echo "OK $s (server.py + $n tool schemas)"
done
TOTAL=$(find "$BASE" -name '*.tool.yaml' 2>/dev/null | wc -l | tr -d ' ')
echo "total_tool_schemas=$TOTAL"
if [[ "${TOTAL:-0}" -lt 40 ]]; then
  echo "FAIL expected >=40 tool schemas, got $TOTAL"; FAIL=1
fi
# Advertise ↔ execute contract (YAML id leaf must exist as FastMCP fn)
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "FAIL no python for execute-contract check"; FAIL=1; PY=""
fi
if [[ -n "$PY" ]]; then
  if ! $PY "$ROOT/scripts/verify-mcp-execute-contract.py"; then
    FAIL=1
  fi
fi
if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
echo "mcp-templates OK"
