#!/usr/bin/env bash
# Generate ops/nginx/obs.htpasswd from GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD.
# Usage: bash scripts/gen-obs-htpasswd.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

USER="${GRAFANA_ADMIN_USER:-admin}"
PASS="${GRAFANA_ADMIN_PASSWORD:-}"
OUT="${1:-ops/nginx/obs.htpasswd}"

if [[ -z "$PASS" ]]; then
  echo "GRAFANA_ADMIN_PASSWORD is required (set in .env)" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
# Prefer htpasswd; fall back to openssl apr1.
if command -v htpasswd >/dev/null 2>&1; then
  htpasswd -nbB "$USER" "$PASS" >"$OUT"
elif command -v openssl >/dev/null 2>&1; then
  HASH="$(openssl passwd -apr1 "$PASS")"
  printf '%s:%s\n' "$USER" "$HASH" >"$OUT"
else
  echo "Need htpasswd or openssl to generate $OUT" >&2
  exit 1
fi
chmod 644 "$OUT"
echo "Wrote $OUT for user=$USER"
