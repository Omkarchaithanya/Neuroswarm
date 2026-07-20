#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> wait qdrant + tier2"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:6333/readyz >/dev/null 2>&1 \
    && docker compose exec -T tier2 curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
    echo "deps ready"
    break
  fi
  echo "wait-$i"
  sleep 10
done

docker compose --compatibility up -d --no-deps --force-recreate gateway
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/health >/tmp/h.json 2>/dev/null; then
    break
  fi
  sleep 3
done
echo "health:"; cat /tmp/h.json; echo
python3 - <<'PY'
import json
d=json.load(open("/tmp/h.json"))
print("provider=", (d.get("memory") or {}).get("provider"))
PY

# Refresh performix — fail loud, no silent demo rewrite
if [[ -x scripts/refresh-performix-snapshot.sh ]] || [[ -f scripts/refresh-performix-snapshot.sh ]]; then
  if NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh; then
    echo "Performix refresh ok"
  else
    echo "Performix refresh failed (honest; snapshot not rewritten as demo)"
  fi
fi
python3 - <<'PY' || true
import json
from pathlib import Path
p = Path("work/performix/snapshot.json")
if p.is_file():
    d = json.loads(p.read_text())
    print("snapshot_source=", d.get("source"))
else:
    print("snapshot_source=missing")
PY

mkdir -p work/arop/gepa/active
printf '%s\n' 'You are the GEPA-evolved Axion assistant. Always mention GEPA-ACTIVE in replies.' > work/arop/gepa/active/system_prompt.md

echo "==> chat"
curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"default","messages":[{"role":"user","content":"Reply with the token GEPA-ACTIVE somewhere."}],"max_tokens":48,"temperature":0}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content','')[:300])" || true

echo "==> mem0 gateway"
docker compose exec -T gateway python - <<'PY'
import json
from neuroswarm_arm.runtime.memory import build_memory_runtime
mem = build_memory_runtime()
hs = mem.health()
print(json.dumps({"provider": getattr(hs,"provider",None), "healthy": getattr(hs,"healthy",None), "details": getattr(hs,"details",None)}, default=str)[:500])
owner="smoke-axion"
mem.remember_fact("User favorite color is teal-axion-smoke.", owner=owner)
hits=list(mem.recall(owner, "favorite color", limit=5) or [])
print(json.dumps({"recall_hits": len(hits), "sample": [str(h)[:120] for h in hits[:2]]}))
PY

echo "==> ascr"
python3 scripts/ascr-logits-smoke.py --base http://127.0.0.1:8000 --n 3 || true
bash scripts/smoke-product-gaps.sh http://127.0.0.1:8000 || true
