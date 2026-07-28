#!/usr/bin/env bash
# Live layer verification matrix on Axion (Compose). Writes JSON snippets under work/layer-verify/
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BASE="${1:-http://127.0.0.1:8000}"
OUT="work/layer-verify"
mkdir -p "$OUT"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "layer-verify start $TS base=$BASE"

json_get() {
  python3 - "$@" <<'PY'
import json,sys
path=sys.argv[1]
keys=sys.argv[2:]
with open(path,encoding="utf-8") as f:
    d=json.load(f)
cur=d
for k in keys:
    if isinstance(cur,dict):
        cur=cur.get(k)
    else:
        cur=None
        break
print("" if cur is None else (json.dumps(cur) if not isinstance(cur,(str,int,float,bool)) else cur))
PY
}

echo "==> 0 compose / k3s"
{
  docker compose ps --format '{{.Name}} {{.Image}} {{.Status}}' 2>/dev/null | head -40 || true
  systemctl is-active k3s 2>/dev/null || echo k3s_inactive
  curl -fsS --max-time 2 http://127.0.0.1:30080/health >/dev/null 2>&1 && echo k8s_30080_up || echo k8s_30080_down
} | tee "$OUT/00-compose.txt"

echo "==> 1 health / NUMA / HAOE"
curl -fsS --max-time 20 "$BASE/health" -o "$OUT/01-health.json" || echo '{"error":"health_fail"}' > "$OUT/01-health.json"
python3 - <<PY
import json
from pathlib import Path
d=json.loads(Path("$OUT/01-health.json").read_text(encoding="utf-8"))
Path("$OUT/01-health-summary.json").write_text(json.dumps({
  "status": d.get("status"),
  "memory": d.get("memory"),
  "numa": d.get("numa") or d.get("topology") or d.get("locality"),
  "haoe": d.get("haoe"),
  "keys": sorted(d.keys())[:40],
}, indent=2), encoding="utf-8")
print(Path("$OUT/01-health-summary.json").read_text())
PY

echo "==> 2 chat cascade"
curl -fsS --max-time 180 -X POST "$BASE/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"cascade","messages":[{"role":"user","content":"Reply in one short sentence: what is Arm Neoverse?"}],"max_tokens":128,"stream":false}' \
  -o "$OUT/02-chat.json" || echo '{"error":"chat_fail"}' > "$OUT/02-chat.json"
python3 - <<PY
import json
from pathlib import Path
d=json.loads(Path("$OUT/02-chat.json").read_text(encoding="utf-8"))
choice=(d.get("choices") or [{}])[0]
msg=((choice.get("message") or {}).get("content")) or d.get("error") or ""
meta={k:d.get(k) for k in ("tier_used","model","usage","id","object") if k in d}
# also dig nested
for k in ("tier_used","cascade","ascr","meta"):
    if k in d: meta[k]=d[k]
Path("$OUT/02-chat-summary.json").write_text(json.dumps({"ok": "error" not in d, "preview": str(msg)[:240], "meta": meta, "top_keys": sorted(d.keys())[:30]}, indent=2), encoding="utf-8")
print(Path("$OUT/02-chat-summary.json").read_text())
PY

echo "==> 3 metrics scrape (ASCR / budget / performix / sve / router)"
curl -fsS --max-time 30 "$BASE/metrics" -o "$OUT/03-metrics.txt" || true
python3 - <<PY
import re
from pathlib import Path
text=Path("$OUT/03-metrics.txt").read_text(encoding="utf-8", errors="replace")
want=re.compile(r'^(nexus_ascr_|ascr_|nexus_performix_|nexus_hw_sve|budget_|nexus_budget_|router_|nexus_router_|admit_|haoe_|nexus_haoe_|nexus_dipa_cascade)')
rows=[]
for line in text.splitlines():
    if not line or line.startswith("#"):
        continue
    if want.search(line) or "sve2" in line.lower() or "speculation_gain" in line or "quality_cascade" in line:
        rows.append(line)
Path("$OUT/03-metrics-filtered.txt").write_text("\n".join(rows[:200])+"\n", encoding="utf-8")
print("filtered_lines", len(rows))
for r in rows[:40]:
    print(r)
PY

echo "==> 4 AQR pick_quant"
python3 - <<PY
from pathlib import Path
import json
out={}
try:
    from neuroswarm_arm.runtime.aqr import pick_quant_primary
except Exception:
    from neuroswarm_arm.aqr import pick_quant_primary
for role in ("reasoning","tool_call","coding","planner","reviewer","default"):
    try:
        out[role]=str(pick_quant_primary(role))
    except TypeError:
        out[role]=str(pick_quant_primary(role=role)) if False else str(pick_quant_primary(role))
    except Exception as e:
        try:
            out[role]=str(pick_quant_primary(role))
        except Exception as e2:
            out[role]=f"ERR:{e2}"
# prove no codebook API
import neuroswarm_arm.runtime.aqr as aqr_mod
src=Path(aqr_mod.__file__).read_text(encoding="utf-8", errors="replace") if hasattr(aqr_mod,"__file__") else ""
out["_codebook_mentions_in_package"]=sum(1 for p in Path("neuroswarm_arm/runtime/aqr").rglob("*.py") for line in p.read_text(encoding="utf-8",errors="replace").splitlines() if "codebook" in line.lower() or "vector register" in line.lower())
Path("$OUT/04-aqr.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
PY

echo "==> 5 ASCR logits smoke"
python3 scripts/ascr-logits-smoke.py --base "$BASE" --n 3 2>&1 | tee "$OUT/05-ascr-smoke.txt" || true

echo "==> 6 router accuracy (quick)"
if [[ -f benchmarks/router_accuracy.py ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv run python benchmarks/router_accuracy.py 2>&1 | tee "$OUT/06-router-accuracy.txt" | tail -40 || true
  elif [[ -x .venv/bin/python ]]; then
    .venv/bin/python benchmarks/router_accuracy.py 2>&1 | tee "$OUT/06-router-accuracy.txt" | tail -40 || true
  else
    PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 benchmarks/router_accuracy.py 2>&1 | tee "$OUT/06-router-accuracy.txt" | tail -40 || true
  fi
else
  echo "missing benchmarks/router_accuracy.py" | tee "$OUT/06-router-accuracy.txt"
fi

echo "==> 7 MCP templates"
if [[ -f scripts/verify-mcp-templates.sh ]]; then
  bash scripts/verify-mcp-templates.sh 2>&1 | tee "$OUT/07-mcp-templates.txt" | tail -30 || true
else
  echo "missing scripts/verify-mcp-templates.sh" | tee "$OUT/07-mcp-templates.txt"
fi

echo "==> 8 budget / economics endpoints"
curl -fsS --max-time 20 "$BASE/v1/cost/economics?limit=20" -o "$OUT/08-economics.json" || echo '{"error":"economics_fail"}' > "$OUT/08-economics.json"
curl -fsS --max-time 20 "$BASE/v1/cost/comparisons?limit=20" -o "$OUT/08-comparisons.json" || true
head -c 400 "$OUT/08-economics.json"; echo

echo "==> 9 AROP optimize + GEPA"
curl -fsS --max-time 120 -X POST "$BASE/arop/optimize" -H "Content-Type: application/json" -d '{"force":true}' -o "$OUT/09-arop-optimize.json" || echo '{"error":"arop_fail"}' > "$OUT/09-arop-optimize.json"
curl -fsS --max-time 30 "$BASE/arop/metrics" -o "$OUT/09-arop-metrics.json" || true
ls -la work/arop/gepa/active 2>/dev/null | tee "$OUT/09-gepa-active.txt" || echo "no gepa active" | tee "$OUT/09-gepa-active.txt"
if [[ -f scripts/smoke-gepa-e2e.sh ]]; then
  bash scripts/smoke-gepa-e2e.sh "$BASE" 2>&1 | tee "$OUT/09-gepa-e2e.txt" | tail -50 || true
fi

echo "==> 10 Performix snapshot status"
python3 - <<PY
import json
from pathlib import Path
p=Path("work/performix/snapshot.json")
d=json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"missing":True}
hs=d.get("hotspots") or []
summary={"exists":p.exists(),"source":d.get("source"),"ipc":d.get("ipc"),"n_hotspots":len(hs),"top":(hs[0] if hs else None),"error":d.get("error")}
Path("$OUT/10-performix.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
PY

echo "==> 11 SGLang arm64 verify"
bash scripts/verify-sglang-arm64.sh 2>&1 | tee "$OUT/11-sglang.txt" | tail -40 || true

echo "==> 12 product gaps smoke"
bash scripts/smoke-product-gaps.sh "$BASE" 2>&1 | tee "$OUT/12-product-gaps.txt" | tail -60 || true

echo "==> 13 Kleidi image proof"
{
  docker compose ps tier1 tier2 tier3 2>/dev/null || true
  docker image inspect nexus-arm/llama-kleidiai:server --format 'Id={{.Id}} Created={{.Created}}' 2>/dev/null || echo "kleidi_image_missing"
} | tee "$OUT/13-kleidi.txt"

echo "==> 14 MAKS multi-agent dedup"
MAKS_OUT="$ROOT/work/benchmarks/maks_multi_agent_dedup.json"
if command -v uv >/dev/null 2>&1; then
  uv run python benchmarks/maks_multi_agent_dedup_bench.py --out "$MAKS_OUT" \
    || printf '{"status":"error"}\n' > "$MAKS_OUT"
else
  python3 benchmarks/maks_multi_agent_dedup_bench.py --out "$MAKS_OUT" \
    || printf '{"status":"error"}\n' > "$MAKS_OUT"
fi
mkdir -p "$ROOT/docs/evidence/latest/layer-verify"
cp -f "$MAKS_OUT" "$OUT/14-maks-dedup.json"
cp -f "$MAKS_OUT" "$ROOT/docs/evidence/latest/layer-verify/14-maks-dedup.json"

echo "layer-verify done $(date -u +%Y-%m-%dT%H:%M:%SZ) → $OUT"
ls -la "$OUT" | head -40
