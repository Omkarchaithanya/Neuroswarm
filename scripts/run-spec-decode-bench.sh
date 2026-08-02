#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"

export PYTHONPATH="${HOME}/neuroswarm-arm${PYTHONPATH:+:${PYTHONPATH}}"
export NSA_TIER_SPEC_URL="${NSA_TIER_SPEC_URL:-http://127.0.0.1:8084}"
export NSA_TIER2_URL="${NSA_TIER2_URL:-http://127.0.0.1:8082}"

python3 -m pytest tests/runtime/dipa/test_spec_decode_wiring.py -q -c /dev/null --rootdir=. --override-ini=addopts= || \
  python -m pytest tests/runtime/dipa/test_spec_decode_wiring.py -q -c /dev/null --rootdir=. --override-ini=addopts=

python3 benchmarks/spec_decode_native.py --rounds 3 || \
  python benchmarks/spec_decode_native.py --rounds 3

ls -lh docs/evidence/spec_decode/
