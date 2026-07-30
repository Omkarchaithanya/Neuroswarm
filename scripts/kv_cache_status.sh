#!/usr/bin/env bash
# Live KV cache status for tier1/2/3 llama-server (:8081-8083).
# Usage: bash scripts/kv_cache_status.sh [--tier 1|2|3|all] [--json] [--watch 5]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec python3 scripts/kv_cache_status.py "$@"
