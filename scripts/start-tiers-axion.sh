#!/usr/bin/env bash
# Reliable Axion tier startup: tier3 first (needs most RAM), then tier1/tier2.
# Usage: cd ~/neuroswarm-arm && bash scripts/start-tiers-axion.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi
COMPOSE=("${DOCKER[@]}" compose -f docker-compose.yaml)

section() { printf '\n== %s ==\n' "$1"; }

set_env() {
  local key="$1"
  local val="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

wait_tier() {
  local name="$1" port="$2" max="${3:-120}"
  local i status
  for i in $(seq 1 "$max"); do
    status="$("${COMPOSE[@]}" ps "$name" --format '{{.Status}}' 2>/dev/null || echo unknown)"
    if echo "$status" | grep -qi restarting; then
      echo "FAIL: $name crash loop"
      "${COMPOSE[@]}" logs "$name" --tail 25
      return 1
    fi
    if curl -fsS "http://127.0.0.1:${port}/props" >/dev/null 2>&1; then
      echo "$name READY on :$port (${status})"
      return 0
    fi
    if (( i % 6 == 0 )); then
      echo "  ... still waiting for $name ($i/${max}) status=$status"
    fi
    sleep 10
  done
  echo "FAIL: $name not ready on :$port"
  "${COMPOSE[@]}" logs "$name" --tail 30
  return 1
}

section "0. Cleanup"
rm -f docker-compose.tier3-fix.yaml

section "1. Reset tier3 slots volume (prevents crash loop)"
"${COMPOSE[@]}" stop tier1 tier2 tier3 2>/dev/null || true
"${DOCKER[@]}" volume rm neuroswarm-arm_tier3-slots 2>/dev/null || true

section "2. Env + models (Axion-safe batching; tier3 reasoning off in compose)"
touch .env
set_env NSA_LLAMA_N_PARALLEL "${NSA_LLAMA_N_PARALLEL:-4}"
set_env NSA_LLAMA_CTX_SIZE "${NSA_LLAMA_CTX_SIZE:-4096}"
set_env NSA_LLAMA_IMAGE "${NSA_LLAMA_IMAGE:-nexus-arm/llama-kleidiai:server}"
set_env TIER3_PARALLEL "${TIER3_PARALLEL:-2}"
set_env TIER3_CTX "${TIER3_CTX:-4096}"
set_env TIER3_THREADS "${TIER3_THREADS:-3}"
set_env TIER3_MODEL "${TIER3_MODEL:-DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf}"
sed -i '/^TIER1_PARALLEL=/d;/^TIER2_PARALLEL=/d' .env 2>/dev/null || true

section "2b. Ensure compose model symlinks"
if ! bash scripts/ensure-compose-models.sh; then
  echo "FAIL: model files missing — tiers cannot start." >&2
  exit 1
fi

section "3. Start tier3 first (largest model — needs free RAM)"
"${COMPOSE[@]}" up -d --remove-orphans --force-recreate --no-deps tier3
wait_tier tier3 8083 90

section "4. Start tier1, then tier2"
"${COMPOSE[@]}" up -d --remove-orphans --force-recreate --no-deps tier1
wait_tier tier1 8081 60
"${COMPOSE[@]}" up -d --remove-orphans --force-recreate --no-deps tier2
wait_tier tier2 8082 90

section "5. Confirm tier3 still alive after tier1+tier2"
sleep 5
if ! curl -fsS http://127.0.0.1:8083/props >/dev/null 2>&1; then
  echo "tier3 died after starting tier1/tier2 — OOM likely. Restarting tier3 alone..."
  "${COMPOSE[@]}" stop tier1 tier2
  sleep 5
  "${COMPOSE[@]}" up -d --force-recreate --no-deps tier3
  wait_tier tier3 8083 90
  echo "WARN: Running tier3 only. Stop tier1/tier2 to use tier3, or upgrade VM RAM."
fi

section "6. Batching slot verify"
bash scripts/verify-batching-slots.sh

section "7. Status"
"${COMPOSE[@]}" ps tier1 tier2 tier3
free -h

section "8. Chat smoke test tier3 (reasoning must be off)"
curl -fsS http://127.0.0.1:8083/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"tier3","messages":[{"role":"user","content":"What is 2+2? Reply with one word only."}],"max_tokens":32,"temperature":0,"stream":false}' \
  | python3 -c "
import sys, json
r = json.load(sys.stdin)
msg = r['choices'][0]['message']
print('content:', repr(msg.get('content')))
print('reasoning:', repr(msg.get('reasoning_content')))
if not (msg.get('content') or '').strip():
    raise SystemExit('FAIL: tier3 content empty — run: docker inspect tier3 argv | grep reasoning')
print('PASS: tier3 reasoning off')
"

echo "PASS: tiers started with batching + tier3 reasoning off"
