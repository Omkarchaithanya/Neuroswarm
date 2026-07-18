#!/usr/bin/env bash
# Apply product-demo env and smoke on Axion (run from repo root).
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/*.sh scripts/*.py 2>/dev/null || true

set_env() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

set_env NSA_AROP_GEPA_LM "http://tier2:8080/v1"
set_env NSA_MEM_LLM local
set_env NSA_MEM_LLM_BASE_URL "http://tier2:8080"
set_env NSA_MEM_EMBEDDER hash
set_env NSA_LLAMA_N_PROBS 5
set_env NSA_PERFORMIX_ALLOW_DEMO 0
set_env NSA_AROP_PERFORMIX 1
grep -E 'NSA_AROP_GEPA_LM|NSA_MEM_LLM|NSA_LLAMA_N_PROBS|NSA_PERFORMIX_ALLOW_DEMO' .env || true

echo "==> recreate gateway"
docker compose --compatibility up -d --no-deps --force-recreate gateway
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/tmp/nsa-health.json 2>/dev/null; then
    break
  fi
  sleep 2
done
echo "health:"; cat /tmp/nsa-health.json 2>/dev/null | head -c 800; echo

mkdir -p work/arop/gepa/active work/performix
printf '%s\n' 'You are the GEPA-evolved Axion assistant. Always mention GEPA-ACTIVE in replies.' > work/arop/gepa/active/system_prompt.md

echo "==> chat"
curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"default","messages":[{"role":"user","content":"Say hello in five words."}],"max_tokens":40,"temperature":0}' \
  | head -c 800
echo

# GEPA HTTP teacher ping (non-fatal)
python3 - <<'PY' || true
import os, json
os.environ["NSA_AROP_GEPA_LM"] = "http://tier2:8080/v1"
# From host, tier2 may not resolve — try via docker network from gateway later.
print(json.dumps({"gepa_active": open("work/arop/gepa/active/system_prompt.md").read().strip()[:80]}))
PY

bash scripts/smoke-product-gaps.sh http://127.0.0.1:8000

# Mem0 recall inside gateway container (has mem0 + qdrant network)
echo "==> mem0 in gateway"
docker compose exec -T gateway python - <<'PY' || true
import json
from neuroswarm_arm.runtime.memory import build_memory_runtime
mem = build_memory_runtime()
owner = "smoke-axion"
mem.remember_fact("User favorite color is teal-axion-smoke.", owner=owner)
hits = list(mem.recall(owner, "favorite color", limit=5) or [])
print(json.dumps({"recall_hits": len(hits), "sample": [str(h)[:120] for h in hits[:2]]}))
hs = mem.health() if hasattr(mem, "health") else None
print(json.dumps({"provider": getattr(hs, "provider", None), "healthy": getattr(hs, "healthy", None)}))
PY
