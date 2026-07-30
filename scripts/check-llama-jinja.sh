#!/usr/bin/env bash
set -euo pipefail
T=$(docker ps --format '{{.Names}}' | grep -i tier3 | head -1 || true)
echo "tier3=$T"
if [[ -n "$T" ]]; then
  docker exec "$T" sh -c 'command -v llama-server; llama-server --help 2>&1 | grep -iE "jinja|tool" | head -30' || true
fi
grep -n jinja /home/tejaswini2482_gmail_com/neuroswarm-arm/docker-compose.yaml 2>/dev/null || echo "no_jinja_in_compose"
docker ps --format '{{.Names}} {{.Ports}}' | grep -iE 'tier|gateway' || true
