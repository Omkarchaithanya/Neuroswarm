#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"
sed -i 's/\r$//' docker-compose.yaml .env 2>/dev/null || true

export MODEL_DIR=/models
export NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server
export COMPOSE_FILE=docker-compose.yaml

mkdir -p /models/tier1
ln -sfn /models/xLAM-2-1B-fc-r-Q4_0.gguf /models/tier1/qwen2.5-0.5b-instruct-q5_k_m.gguf

echo "=== gate1: compose config ==="
docker compose -f docker-compose.yaml config | grep -A12 '^  tier-spec:' | head -40

echo "=== recreate tier-spec ==="
docker compose -f docker-compose.yaml up -d --force-recreate tier-spec

# Like-for-like baseline: same 0.5B GGUF without --model-draft (host :8082 taken by xLAM).
# Harness CLI still uses --baseline-url; label remains tier2-no-spec in JSON for compatibility.
docker rm -f tier-spec-baseline 2>/dev/null || true
docker run -d --name tier-spec-baseline --restart unless-stopped \
  -p 8085:8080 \
  --cpuset-cpus 2-3 \
  -v /models:/models:ro \
  -v "${NSA_LLAMA_SLOT_DIR:-/tmp/neuroswarm-slots}:/var/lib/ns/slots" \
  nexus-arm/llama-kleidiai:server \
  -m /models/tier1/qwen2.5-0.5b-instruct-q5_k_m.gguf \
  --host 0.0.0.0 --port 8080 -ngl 0 --threads 8 --ctx-size 4096 \
  --cont-batching --parallel 4 --slot-save-path /var/lib/ns/slots --metrics

echo "WAITING health :8084 (spec draft-simple) and :8085 (same GGUF, no draft)"
for n in $(seq 1 60); do
  s=NO; t=NO
  curl -fsS http://127.0.0.1:8084/v1/models >/dev/null 2>&1 && s=OK
  curl -fsS http://127.0.0.1:8085/v1/models >/dev/null 2>&1 && t=OK
  echo "try ${n} spec=${s} baseline=${t}"
  if [[ "${s}" == "OK" && "${t}" == "OK" ]]; then
    echo BOTH_READY
    break
  fi
  sleep 10
done

docker compose -f docker-compose.yaml logs --tail=30 tier-spec || true
docker logs --tail=20 tier-spec-baseline || true

export PYTHONPATH="${HOME}/neuroswarm-arm"
export NSA_TIER_SPEC_URL=http://127.0.0.1:8084
export NSA_TIER2_URL=http://127.0.0.1:8085

echo "=== gate2: unit tests ==="
python3 -m pytest tests/runtime/dipa/test_spec_decode_wiring.py -q -c /dev/null --rootdir=. --override-ini=addopts=

echo "=== gate3+4: native A/B bench ==="
python3 benchmarks/spec_decode_native.py --rounds 3 --baseline-url http://127.0.0.1:8085

ls -lh docs/evidence/spec_decode/
echo "=== ASR snapshot (process-local; bench does not hit DIPA path) ==="
python3 - <<'PY'
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import ASR_METRICS
print(ASR_METRICS.snapshot())
PY
