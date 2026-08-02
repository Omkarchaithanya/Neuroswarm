#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"
export MODEL_DIR=/models
export NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server

echo "=== tier-spec logs ==="
docker compose -f docker-compose.yaml logs --tail=80 tier-spec || true
echo "=== tier-spec inspect state ==="
docker inspect neuroswarm-arm-tier-spec-1 --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}' || true
echo "=== host llama on 8082 ==="
ps -fp 339370 || true
curl -fsS http://127.0.0.1:8082/v1/models | head -c 400 || true
echo
echo "=== try start tier-spec only ==="
docker compose -f docker-compose.yaml up -d tier-spec
sleep 5
docker compose -f docker-compose.yaml logs --tail=40 tier-spec || true
curl -fsS http://127.0.0.1:8084/v1/models | head -c 400 || true
echo
