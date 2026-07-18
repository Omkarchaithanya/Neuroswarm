#!/usr/bin/env bash
# Bring up Docker Compose stack on Axion (idempotent health-gated).
# Usage (on VM): bash scripts/remote-compose-up.sh
# Env: PERFORMIX=1 force profile; REQUIRE_HEALTH=0 soft-fail (default hard-fail); SKIP_BUILD=1 skip rebuild.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Windows sync may leave CRLF on shell scripts.
find scripts -name '*.sh' -print0 2>/dev/null | xargs -0 -r sed -i 's/\r$//' || true

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  else
    echo "Missing .env and .env.example" >&2
    exit 1
  fi
fi

# Ensure Mem0 / hybrid reflection defaults exist on older Axion .env files.
ensure_env() {
  local key="$1"
  local val="$2"
  if ! grep -qE "^${key}=" .env 2>/dev/null; then
    echo "${key}=${val}" >> .env
    echo "Appended ${key} to .env"
  fi
}
set_env() {
  local key="$1"
  local val="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}
ensure_env NSA_MEM_PROVIDER mem0
ensure_env NSA_MEM_STORE /app/work/memory
ensure_env NSA_MEM_QDRANT_PATH /app/work/memory/qdrant
ensure_env NSA_MEM_QDRANT_URL http://qdrant:6333
ensure_env NSA_MEM_LLM none
ensure_env NSA_MEM_LLM_BASE_URL http://tier2:8080
ensure_env NSA_MEM_EMBEDDER hash
ensure_env NSA_AROP_REFLECTION hybrid
ensure_env NSA_AROP_GEPA_LM mock
ensure_env NSA_ASCR_TEXT_AGREE 1
ensure_env NSA_LLAMA_N_PROBS 0

# Optional product-demo knobs (PRODUCT_DEMO=1): real GEPA LM + Mem0 extraction + logits.
if [[ "${PRODUCT_DEMO:-0}" == "1" ]]; then
  set_env NSA_AROP_GEPA_LM "http://tier2:8080/v1"
  set_env NSA_MEM_LLM local
  set_env NSA_MEM_LLM_BASE_URL "http://tier2:8080"
  set_env NSA_MEM_EMBEDDER hash
  set_env NSA_LLAMA_N_PROBS 5
  set_env TIER2_CTX 8192
  echo "==> PRODUCT_DEMO=1 → GEPA http LM, Mem0 local LLM, llama n_probs=5, TIER2_CTX=8192"
fi

mkdir -p work/performix work/swarm work/memory/qdrant work/arop/gepa

# Ensure docker is available (bootstrap-vm may already have installed it).
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; run scripts/bootstrap-vm.sh first" >&2
  exit 1
fi

REQUIRE_HEALTH="${REQUIRE_HEALTH:-1}"
SKIP_BUILD="${SKIP_BUILD:-0}"
PERFORMIX="${PERFORMIX:-0}"

COMPOSE_PROFILES=()
if [[ "$PERFORMIX" == "1" ]]; then
  set_env NSA_AROP_PERFORMIX_MCP "http://performix-bridge:8090"
  COMPOSE_PROFILES=(--profile performix)
  echo "==> performix profile forced (PERFORMIX=1)"
elif grep -qE '^NSA_AROP_PERFORMIX_MCP=https?://' .env 2>/dev/null; then
  COMPOSE_PROFILES=(--profile performix)
  echo "==> performix profile enabled (NSA_AROP_PERFORMIX_MCP set)"
fi

BUILD_ARGS=(up -d)
if [[ "$SKIP_BUILD" != "1" ]]; then
  BUILD_ARGS=(up --build -d)
fi

# Free host :80 from k3s Traefik before publishing Compose nginx.
if [[ -x scripts/free-host-port80-for-compose.sh ]]; then
  bash scripts/free-host-port80-for-compose.sh || true
fi

echo "==> docker compose ${BUILD_ARGS[*]}"
docker compose --compatibility "${COMPOSE_PROFILES[@]}" "${BUILD_ARGS[@]}"
# Avoid stale upstream IP after gateway recreate
docker compose restart proxy 2>/dev/null || true
bash scripts/free-host-port80-for-compose.sh || true

wait_http() {
  local url="$1"
  local label="$2"
  local tries="${3:-45}"
  local i code
  for ((i = 1; i <= tries; i++)); do
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo FAIL)"
    if [[ "$code" == "200" ]]; then
      echo "OK $label ($url)"
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for $label at $url (last_code=${code:-?})" >&2
  docker compose ps || true
  return 1
}

HEALTH_OK=0
if wait_http "http://127.0.0.1/health" "health" 25; then
  wait_http "http://127.0.0.1/ready" "ready" 20 || true
  HEALTH_OK=1
elif wait_http "http://127.0.0.1:8000/health" "health" 45; then
  wait_http "http://127.0.0.1:8000/ready" "ready" 45 || true
  HEALTH_OK=1
  echo "WARN: gateway :8000 healthy but proxy :80 not — Traefik may still own :80" >&2
  bash scripts/free-host-port80-for-compose.sh || true
  docker compose up -d --force-recreate proxy || true
  if wait_http "http://127.0.0.1/health" "health-after-free" 20; then
    echo "OK proxy :80 recovered after Traefik free"
  fi
fi

docker compose ps

# Host cron for Performix snapshot refresh when profile is on.
if [[ ${#COMPOSE_PROFILES[@]} -gt 0 ]]; then
  ensure_env NSA_AROP_PERFORMIX 1
  CRON_LINE="*/2 * * * * cd $ROOT && NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh >>work/performix/refresh.log 2>&1"
  if command -v crontab >/dev/null 2>&1; then
    (crontab -l 2>/dev/null | grep -v refresh-performix-snapshot.sh; echo "$CRON_LINE") | crontab - || true
    echo "==> performix refresh cron installed (every 2 min)"
  fi
fi

if [[ "$HEALTH_OK" != "1" ]]; then
  echo "remote-compose-up: health probe FAILED" >&2
  if [[ "$REQUIRE_HEALTH" == "0" ]]; then
    echo "REQUIRE_HEALTH=0 — continuing after failed probe" >&2
    exit 0
  fi
  exit 1
fi

echo "remote-compose-up: success"
