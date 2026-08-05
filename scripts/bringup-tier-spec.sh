#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"

# Normalize Windows CRLF that breaks image tags / compose.
sed -i 's/\r$//' .env docker-compose.yaml docker-compose.local.yaml 2>/dev/null || true

export MODEL_DIR=/models
export NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server
export COMPOSE_FILE=docker-compose.yaml

mkdir -p "${MODEL_DIR}/tier1"
TARGET="${MODEL_DIR}/tier1/qwen2.5-0.5b-instruct-q5_k_m.gguf"
if [[ ! -e "${TARGET}" ]]; then
  ln -sfn "${MODEL_DIR}/xLAM-2-1B-fc-r-Q4_0.gguf" "${TARGET}"
fi
ls -lh "${MODEL_DIR}/tier1/"

docker compose -f docker-compose.yaml config | grep -A8 '^  tier-spec:' | head -40
docker compose -f docker-compose.yaml up -d tier-spec tier2

echo "WAITING health on :8084 and :8082"
for n in $(seq 1 60); do
  s=NO
  t=NO
  if curl -fsS http://127.0.0.1:8084/v1/models >/dev/null 2>&1; then s=OK; fi
  if curl -fsS http://127.0.0.1:8082/v1/models >/dev/null 2>&1; then t=OK; fi
  echo "try ${n} spec=${s} tier2=${t}"
  if [[ "${s}" == "OK" && "${t}" == "OK" ]]; then
    echo BOTH_READY
    break
  fi
  sleep 10
done

docker compose -f docker-compose.yaml ps tier-spec tier2
docker compose -f docker-compose.yaml logs --tail=40 tier-spec || true
