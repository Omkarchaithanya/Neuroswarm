#!/usr/bin/env bash
# AROP preflight — Axion honesty gates before live --apply.
# Usage: NSA_PERFORMIX_ALLOW_DEMO=0 bash scripts/arop-preflight.sh [path/to/code_hotspots.json]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
HOTSPOTS="${1:-work/arop/performix/code-hotspots.json}"
export NSA_PERFORMIX_ALLOW_DEMO="${NSA_PERFORMIX_ALLOW_DEMO:-0}"
exec python3 -m neuroswarm_arm.arop.preflight "$HOTSPOTS"
