#!/usr/bin/env bash
# Leftovers verify: Performix honesty, GEPA HTTP e2e, Mem0 extraction, ASCR logits.
# Usage (on Axion): PRODUCT_DEMO=1 bash scripts/axion-product-verify.sh
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

# Demo knobs for leftovers proof
set_env NSA_AROP_GEPA_LM "http://tier2:8080/v1"
set_env NSA_MEM_LLM local
set_env NSA_MEM_LLM_BASE_URL "http://tier2:8080"
set_env NSA_MEM_EMBEDDER hash
set_env NSA_LLAMA_N_PROBS 5
set_env NSA_PERFORMIX_ALLOW_DEMO 0
set_env NSA_AROP_PERFORMIX 1
set_env TIER2_CTX 8192

echo "==> recreate tier2 (8k ctx) + gateway"
docker compose --compatibility up -d --no-deps --force-recreate tier2 gateway
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8000/health >/tmp/h.json 2>/dev/null \
    && docker compose exec -T tier2 curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
echo "health:"; python3 -c "import json;d=json.load(open('/tmp/h.json'));print('provider', d.get('memory',{}).get('provider'), 'status', d.get('status'))"

echo "==> Performix refresh (expect apx|unavailable)"
set +e
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh
echo "refresh_rc=$?"
set -e
python3 - <<'PY'
import json, sys
from pathlib import Path
p = Path("work/performix/snapshot.json")
if not p.is_file():
    print("FAIL: missing snapshot after refresh"); sys.exit(1)
src = json.loads(p.read_text()).get("source")
print("snapshot_source=", src)
if src not in {"apx", "unavailable"}:
    print("FAIL: expected source=apx|unavailable, got", src); sys.exit(1)
print("OK: performix honesty")
PY

echo "==> GEPA HTTP e2e"
bash scripts/smoke-gepa-e2e.sh http://127.0.0.1:8000

echo "==> Mem0 chat extraction"
docker compose exec -T gateway python - <<'PY'
import json, time
from neuroswarm_arm.runtime.memory import build_memory_runtime
m = build_memory_runtime()
h = m.health()
print("provider", getattr(h, "provider", None))
owner = "smoke-extract"
# Chat-style messages trigger infer=True path (lean extraction prompt).
msgs = [
    {"role": "user", "content": "Please remember: my favorite color is teal-axion-extract."},
    {"role": "assistant", "content": "Got it — I'll remember your favorite color is teal-axion-extract."},
]
m.remember(msgs, owner=owner, agent_id=owner)
time.sleep(1)
hits = list(m.recall(owner, "favorite color", limit=5) or [])
print(json.dumps({"recall_hits": len(hits), "sample": [str(x)[:120] for x in hits[:3]]}))
if not hits:
    raise SystemExit("FAIL: empty recall after chat remember")
print("OK: mem0 recall")
PY

echo "==> ASCR logits"
python3 scripts/ascr-logits-smoke.py --base http://127.0.0.1:8000 --n 2

echo "==> smoke-product-gaps"
bash scripts/smoke-product-gaps.sh http://127.0.0.1:8000

echo "==> leftovers verify done"
