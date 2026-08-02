#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"
export PYTHONPATH="${HOME}/neuroswarm-arm"
export NSA_TIER_SPEC_URL=http://127.0.0.1:8084
export NSA_TIER2_URL=http://127.0.0.1:8085

# Prefer project venv / uv if present; otherwise bare python3 (bench has tenacity fallback).
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
elif command -v uv >/dev/null 2>&1; then
  PY="uv run python"
else
  PY=python3
fi

$PY benchmarks/spec_decode_native.py --rounds 3 --baseline-url http://127.0.0.1:8085
ls -lh docs/evidence/spec_decode/
