#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

T2_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' neuroswarm-arm-tier2-1 2>/dev/null || true)"
if [[ -z "${T2_IP}" ]]; then
  echo "tier2 container IP not found" >&2
  exit 1
fi
TIER2_URL="http://${T2_IP}:8080"

echo "=== phase0 file proof ==="
grep -c median_tok_s scripts/validate_kleidiai.py
grep -c kleidiai_detected scripts/validate_kleidiai.py || true
wc -l scripts/validate_kleidiai.py
test -f benchmarks/kleidiai_baselines.json

echo "=== tier2 health ==="
curl -fsS "${TIER2_URL}/health"

echo "=== validator ==="
python3 scripts/validate_kleidiai.py --url "${TIER2_URL}"
