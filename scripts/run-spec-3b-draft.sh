#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"
sed -i 's/\r$//' docker-compose.yaml 2>/dev/null || true

export MODEL_DIR=/models
export NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server

mkdir -p /models/tier1
ln -sfn /models/xLAM-2-1B-fc-r-Q4_0.gguf /models/tier1/qwen2.5-0.5b-instruct-q5_k_m.gguf

docker compose -f docker-compose.yaml up -d --force-recreate tier-spec

# Baseline: plain 3B, no draft (host :8082 occupied by xLAM)
docker rm -f tier-spec-baseline 2>/dev/null || true
docker run -d --name tier-spec-baseline --restart unless-stopped \
  -p 8085:8080 \
  --cpuset-cpus 5-7 \
  -v /models:/models:ro \
  nexus-arm/llama-kleidiai:server \
  -m /models/xLAM-2-3B-fc-r-Q4_0.gguf \
  --host 0.0.0.0 --port 8080 -ngl 0 --threads 3 --ctx-size 4096 \
  --cont-batching --parallel 4 --metrics

echo "WAITING :8084 (3B+0.5B draft) vs :8085 (3B alone)"
for n in $(seq 1 90); do
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

docker compose -f docker-compose.yaml logs --tail=25 tier-spec || true

export PYTHONPATH="${HOME}/neuroswarm-arm"
export NSA_TIER_SPEC_URL=http://127.0.0.1:8084
python3 benchmarks/spec_decode_native.py --rounds 3 --baseline-url http://127.0.0.1:8085
ls -lh docs/evidence/spec_decode/
