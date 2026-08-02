#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"

export MODEL_DIR=/models
export NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server
export COMPOSE_FILE=docker-compose.yaml

echo "=== port 8082 holders ==="
sudo ss -ltnp | grep 8082 || ss -ltnp | grep 8082 || true
docker ps -a --format '{{.Names}} {{.Status}} {{.Ports}}' | grep -E '8082|tier2|tier-spec' || true

# Stop stale binders on 8082, keep tier-spec.
docker ps -aq --filter publish=8082 | xargs -r docker rm -f || true
# Also remove failed recreate container if present
docker rm -f neuroswarm-arm-tier2-1 2>/dev/null || true

MODEL_DIR=/models NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server \
  docker compose -f docker-compose.yaml up -d tier2 tier-spec

echo "WAITING health"
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
docker compose -f docker-compose.yaml logs --tail=20 tier-spec || true
docker compose -f docker-compose.yaml logs --tail=20 tier2 || true

export PYTHONPATH="${HOME}/neuroswarm-arm"
export NSA_TIER_SPEC_URL=http://127.0.0.1:8084
export NSA_TIER2_URL=http://127.0.0.1:8082

python3 -m pytest tests/runtime/dipa/test_spec_decode_wiring.py -q -c /dev/null --rootdir=. --override-ini=addopts= \
  || python -m pytest tests/runtime/dipa/test_spec_decode_wiring.py -q -c /dev/null --rootdir=. --override-ini=addopts=

python3 benchmarks/spec_decode_native.py --rounds 3 \
  || python benchmarks/spec_decode_native.py --rounds 3

ls -lh docs/evidence/spec_decode/
