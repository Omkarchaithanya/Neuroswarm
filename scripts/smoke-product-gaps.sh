#!/usr/bin/env bash
# Product Gaps Polish smoke (Compose path on Axion or local).
# Checks: Performix snapshot honesty, GEPA active prompt, Mem0 health, ASCR mode label.
# Usage: bash scripts/smoke-product-gaps.sh [BASE_URL]
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> health @ ${BASE}"
HEALTH="$(curl -fsS "${BASE}/health" || true)"
echo "$HEALTH" | head -c 800
echo

PROVIDER="$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); m=d.get('memory') or {}; print(m.get('provider') or d.get('provider') or '?')" 2>/dev/null || echo "?")"
echo "memory.provider=${PROVIDER}"

echo "==> Performix snapshot"
SNAP="work/performix/snapshot.json"
if [[ -f "$SNAP" ]]; then
  SRC="$(python3 - <<'PY' 2>/dev/null || echo unknown
import json
from pathlib import Path
d = json.loads(Path("work/performix/snapshot.json").read_text(encoding="utf-8"))
src = d.get("source") or (d.get("meta") or {}).get("source") or ""
if not src and d.get("error"):
    src = "unavailable"
print(src or "unknown")
PY
)"
  echo "snapshot source=${SRC}"
  if [[ "$SRC" == "apx" || "$SRC" == "unavailable" ]]; then
    echo "OK: honest Performix source=${SRC}"
  elif [[ "$SRC" == "demo" || "$SRC" == "synthetic" ]]; then
    if [[ "${NSA_PERFORMIX_ALLOW_DEMO:-0}" == "1" ]]; then
      echo "INFO: synthetic/demo snapshot (ALLOW_DEMO=1)"
    else
      echo "FAIL: leftover demo on disk (expect source=apx|unavailable when live required)" >&2
      exit 1
    fi
  fi
else
  echo "INFO: no snapshot yet (honest empty — refresh after apx prepare)"
fi

echo "==> GEPA active prompt"
ACTIVE="work/arop/gepa/active/system_prompt.md"
if [[ -f "$ACTIVE" ]]; then
  echo "active system_prompt present ($(wc -c < "$ACTIVE") bytes)"
else
  echo "INFO: no active GEPA prompt yet — run optimize→approve→deploy first"
fi

echo "==> Mem0 remember/recall (in-process when NSA_MEM_LLM=local)"
python3 - <<'PY' || true
import json
try:
    from neuroswarm_arm.runtime.memory import build_memory_runtime
    mem = build_memory_runtime()
    neuro = mem if hasattr(mem, "remember_fact") else getattr(mem, "neuro", mem)
    owner = "smoke-product-gaps"
    fact = "User favorite color is teal-axion-smoke."
    if hasattr(neuro, "remember_fact"):
        neuro.remember_fact(fact, owner=owner)
    elif hasattr(neuro, "remember"):
        neuro.remember(fact, owner=owner)
    hits = list(neuro.recall(owner, "favorite color", limit=5) or []) if hasattr(neuro, "recall") else []
    print(json.dumps({"recall_hits": len(hits), "sample": str(hits[:2])[:200], "provider": getattr(neuro, "provider_name", "?")}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
PY

echo "==> ASCR logits smoke"
python3 scripts/ascr-logits-smoke.py --base "$BASE" --n "${ASCR_SMOKE_N:-3}" || true

echo "==> done"
