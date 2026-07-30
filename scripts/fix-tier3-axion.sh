#!/usr/bin/env bash
# Recover tier3 on Axion: stop crash loop, fix slots volume, start with reasoning off.
# Usage: cd ~/neuroswarm-arm && bash scripts/fix-tier3-axion.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

COMPOSE=("${DOCKER[@]}" compose -f docker-compose.yaml -f docker-compose.tier3-reasoning.yaml)
if ! "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  COMPOSE=(sudo docker compose -f docker-compose.yaml -f docker-compose.tier3-reasoning.yaml)
fi

section() { printf '\n== %s ==\n' "$1"; }

section "1. Remove broken override (causes crash loop)"
rm -f docker-compose.tier3-fix.yaml

section "2. Stop tier3 and reset slots volume"
"${COMPOSE[@]}" stop tier1 tier2 tier3 2>/dev/null || true
"${COMPOSE[@]}" rm -f tier3 2>/dev/null || true
VOLUME_NAME="$("${COMPOSE[@]}" config --format json 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('volumes',{}).get('tier3-slots',{}).get('name','neuroswarm-arm_tier3-slots'))" \
  2>/dev/null || echo "neuroswarm-arm_tier3-slots")"
"${DOCKER[@]}" volume rm "$VOLUME_NAME" 2>/dev/null || true
echo "Reset volume: $VOLUME_NAME"

section "3. Ensure tier3 env"
touch .env
for kv in TIER3_CTX=4096 TIER3_PARALLEL=2 TIER3_THREADS=3; do
  key="${kv%%=*}"
  if ! grep -q "^${key}=" .env 2>/dev/null; then
    echo "$kv" >> .env
  fi
done

section "4. Start tier3 (reasoning-off override)"
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier3

section "5. Wait for port 8083"
ready=0
for i in $(seq 1 90); do
  status="$("${COMPOSE[@]}" ps tier3 --format '{{.Status}}' 2>/dev/null || echo unknown)"
  if echo "$status" | grep -qi 'restarting'; then
    echo "CRASH LOOP at attempt $i — last logs:"
    "${COMPOSE[@]}" logs tier3 --tail 20
    exit 1
  fi
  if curl -fsS http://127.0.0.1:8083/props >/dev/null 2>&1; then
    ready=1
    echo "tier3 READY after ~$((i * 10))s ($status)"
    curl -fsS http://127.0.0.1:8083/props | \
      python3 -c "import sys,json; d=json.load(sys.stdin); print('model:', d.get('model_path')); print('n_ctx:', d.get('default_generation_settings',{}).get('n_ctx'))"
    break
  fi
  echo "$(date +%H:%M:%S) waiting... ($i/90) status=$status"
  sleep 10
done

if [[ "$ready" -ne 1 ]]; then
  echo "FAIL: tier3 never became ready"
  "${COMPOSE[@]}" logs tier3 --tail 40
  exit 1
fi

section "6. Chat smoke test"
curl -fsS http://127.0.0.1:8083/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"tier3","messages":[{"role":"user","content":"What is 2+2? One word only."}],"max_tokens":16,"temperature":0,"stream":false}' \
  | python3 -c "
import sys, json, re
r = json.load(sys.stdin)
text = (r['choices'][0]['message'].get('content') or '').strip()
text = re.sub(r'(?s)^.*?\s*', '', text).strip()
print('answer:', text)
print('usage:', r.get('usage'))
"

section "7. Restart tier1 and tier2 (sequential — avoids OOM killing tier3)"
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier1
for i in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8081/props >/dev/null 2>&1 && break
  sleep 5
done
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier2
for i in $(seq 1 90); do
  curl -fsS http://127.0.0.1:8082/props >/dev/null 2>&1 && break
  sleep 5
done
sleep 10

if ! curl -fsS http://127.0.0.1:8083/props >/dev/null 2>&1; then
  echo "WARN: tier3 died after tier1/tier2 started (host RAM). Stopping tier1/tier2, keeping tier3."
  "${COMPOSE[@]}" stop tier1 tier2
  "${COMPOSE[@]}" up -d --no-deps tier3
  for i in $(seq 1 60); do
    curl -fsS http://127.0.0.1:8083/props >/dev/null 2>&1 && break
    sleep 5
  done
fi

"${COMPOSE[@]}" ps tier1 tier2 tier3
ss -ltnp | grep 8083 || echo "8083 not listening"

echo
echo "PASS: tier3 is up on :8083. Use: docker compose up -d (no tier3-fix override)."
