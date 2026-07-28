#!/usr/bin/env bash
# Apply tier3 reasoning-off override and verify.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yaml -f docker-compose.tier3-reasoning.yaml)

rm -f docker-compose.tier3-fix.yaml

echo "== Recreate tier3 with reasoning off =="
"${COMPOSE[@]}" stop tier3 2>/dev/null || true
"${COMPOSE[@]}" rm -f tier3 2>/dev/null || true
"${COMPOSE[@]}" up -d --force-recreate --no-deps tier3

for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8083/props >/dev/null 2>&1; then
    echo "tier3 ready"
    break
  fi
  sleep 5
done

echo "== Container argv =="
docker inspect neuroswarm-arm-tier3-1 --format '{{range .Config.Cmd}}{{.}} {{end}}' | tr ' ' '\n' | grep -A1 reasoning || {
  echo "FAIL: --reasoning off missing from container"
  exit 1
}

echo "== Chat smoke test =="
curl -fsS http://127.0.0.1:8083/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"tier3","messages":[{"role":"user","content":"What is 2+2? One word only."}],"max_tokens":32,"temperature":0,"stream":false}' \
  | python3 -c "
import sys, json
r = json.load(sys.stdin)
m = r['choices'][0]['message']
print('content:', repr(m.get('content')))
print('reasoning:', repr(m.get('reasoning_content')))
c = (m.get('content') or '').strip()
if not c:
    raise SystemExit('FAIL: content still empty')
print('PASS')
"
