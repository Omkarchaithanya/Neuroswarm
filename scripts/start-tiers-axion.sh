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
COMPOSE=("${DOCKER[@]}" compose -f docker-compose.yaml -f docker-compose.tier3-reasoning.yaml)

section() { printf '\n== %s ==\n' "$1"; }

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

section "2. Env"
touch .env
for kv in TIER3_CTX=4096 TIER3_PARALLEL=1 TIER3_THREADS=3 TIER2_PARALLEL=2 TIER1_PARALLEL=2; do
  key="${kv%%=*}"
  if grep -q "^${key}=" .env 2>/dev/null; then
    sed -i "s/^${key}=.*/${kv}/" .env
  else
    echo "$kv" >> .env
  fi
done

section "3. Start tier3 first (largest model — needs free RAM)"
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier3
wait_tier tier3 8083 90

section "4. Start tier1, then tier2"
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier1
wait_tier tier1 8081 60
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier2
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

section "6. Status"
"${COMPOSE[@]}" ps tier1 tier2 tier3
free -h
ss -ltnp | grep -E '8081|8082|8083' || true

section "7. Chat smoke test tier3"
curl -fsS http://127.0.0.1:8083/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"tier3","messages":[{"role":"user","content":"What is 2+2? Reply with one word only."}],"max_tokens":32,"temperature":0,"stream":false}' \
  | python3 -c "
import sys, json
r = json.load(sys.stdin)
msg = r['choices'][0]['message']
print('content:', repr(msg.get('content')))
print('reasoning:', repr(msg.get('reasoning_content')))
print('usage:', r.get('usage'))
"

echo
echo "PASS: tiers started. If tier3 chat is empty, check: docker compose logs tier3 --tail 20"
