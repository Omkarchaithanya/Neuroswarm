#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/neuroswarm-arm}"
cd "$PROJECT_ROOT"

echo "Waiting for gateway health/ready..."
for i in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    echo "Gateway responding on attempt $i"
    break
  fi
  echo "waiting_$i"
  sleep 5
done

curl -fsS http://127.0.0.1:8000/health
echo
curl -fsS http://127.0.0.1:8000/ready
echo

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi
"${DOCKER[@]}" compose ps

bash scripts/capture-evidence.sh
