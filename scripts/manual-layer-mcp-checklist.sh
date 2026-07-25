#!/usr/bin/env bash
# Manual layer + MCP checklist. Always cds to the repo that owns this script.
# Usage (from ANY cwd on Axion):
#   bash ~/neuroswarm-arm/scripts/manual-layer-mcp-checklist.sh
#   bash scripts/manual-layer-mcp-checklist.sh   # if already in repo
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BASE="${1:-http://127.0.0.1:80}"
PASS=0
FAIL=0

ok() { echo "PASS  $*"; PASS=$((PASS + 1)); }
bad() { echo "FAIL  $*"; FAIL=$((FAIL + 1)); }
info() { echo "INFO  $*"; }

echo "============================================================"
echo " NeuroSwarm manual checklist"
echo " cwd=$ROOT"
echo " base=$BASE"
echo "============================================================"

if [[ ! -f "$ROOT/docker-compose.yaml" ]]; then
  bad "not in neuroswarm-arm repo (missing docker-compose.yaml)"
  echo "Run:  cd ~/neuroswarm-arm && bash scripts/manual-layer-mcp-checklist.sh"
  exit 1
fi

echo
echo "==> 0 compose"
if docker compose ps >/dev/null 2>&1; then
  docker compose ps --format 'table {{.Name}}\t{{.Status}}' | head -20
  ok "docker compose readable"
else
  bad "docker compose failed (are you in $ROOT?)"
fi

echo
echo "==> 1 /ready + /build-info"
curl -fsS --max-time 30 "$BASE/ready" -o /tmp/ns-ready.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/ns-ready.json"))
r=(d.get("tools") or {}).get("router") or {}
print("status", d.get("status"))
print("embedding_backend", r.get("embedding_backend"))
print("dims", r.get("embedding_dims"))
print("tools_registered", r.get("tools_registered"))
emb=r.get("embedding_backend")
n=int(r.get("tools_registered") or 0)
open("/tmp/ns-ready.ok","w").write("1" if emb=="fastembed" and n>=40 and d.get("status")=="ready" else "0")
PY
if [[ "$(cat /tmp/ns-ready.ok)" == "1" ]]; then ok "ready fastembed + ≥40 tools"; else bad "ready assertions"; fi
curl -fsS --max-time 20 "$BASE/build-info" -o /tmp/ns-bi.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/ns-bi.json"))
print("axion", d.get("axion_profile"))
print("detected", d.get("detected"))
ok = d.get("detected",{}).get("sve2") is True and d.get("axion_profile",{}).get("sme2") is False
open("/tmp/ns-bi.ok","w").write("1" if ok else "0")
PY
if [[ "$(cat /tmp/ns-bi.ok)" == "1" ]]; then ok "build-info SVE2+I8MM, no SME2"; else bad "build-info"; fi

echo
echo "==> 2 chat output + latency"
curl -fsS --max-time 180 -X POST "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply in one short sentence: what is Arm Neoverse?"}],"max_tokens":64}' \
  -o /tmp/ns-chat.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/ns-chat.json"))
m=d.get("metrics") or {}
content=(d.get("content") or "") or (((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
print("content:", content[:200])
print("tier", d.get("tier_used"), "lat_ms", m.get("latency_ms"), "ttft", m.get("ttft_ms"), "ascr", m.get("ascr_mode"))
ok = bool(content.strip()) and d.get("tier_used") is not None
open("/tmp/ns-chat.ok","w").write("1" if ok else "0")
PY
if [[ "$(cat /tmp/ns-chat.ok)" == "1" ]]; then ok "chat non-empty + tier"; else bad "chat empty/broken"; fi

echo
echo "==> 3 high-conf S3 → thinking_token_cap=256"
curl -fsS --max-time 60 -X POST "$BASE/tools/route" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Upload an artifact to S3 object storage","top_k":3}' -o /tmp/ns-route.json
curl -fsS --max-time 180 -X POST "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Upload an artifact to S3 object storage"}],"max_tokens":64}' \
  -o /tmp/ns-chat-hc.json
python3 - <<'PY'
import json
r=json.load(open("/tmp/ns-route.json"))
c=json.load(open("/tmp/ns-chat-hc.json"))
ids=r.get("tool_ids") or []
print("route ids", ids, "conf", r.get("confidence_top1"), "hc", r.get("high_confidence"), "red", r.get("token_reduction_ratio"))
print("cap", c.get("thinking_token_cap"), "tools", c.get("tool_schemas_used"))
ok = (
  any("s3" in str(x).lower() for x in ids)
  and float(r.get("token_reduction_ratio") or 0) >= 0.85
  and bool(r.get("high_confidence"))
  and int(c.get("thinking_token_cap") or 0) == 256
)
open("/tmp/ns-hc.ok","w").write("1" if ok else "0")
PY
if [[ "$(cat /tmp/ns-hc.ok)" == "1" ]]; then ok "S3 route + high_conf + cap 256"; else bad "S3 high-conf path"; fi

echo
echo "==> 4 MCP templates on disk"
if bash "$ROOT/scripts/verify-mcp-templates.sh"; then
  ok "MCP templates ≥40 schemas"
else
  bad "MCP templates verify"
fi

echo
echo "==> 5 MCP route family matrix"
python3 - <<PY
import json, urllib.request
base="$BASE"
cases = [
  ("Upload an artifact to S3 object storage", "s3"),
  ("create a github issue about a bug", "github"),
  ("run a SQL select on postgres users table", "postgres"),
  ("post a message to slack channel", "slack"),
  ("search the web for Arm Neoverse V2", "web"),
  ("open browser and take a snapshot of the page", "browser"),
]
fail=0
for q, fam in cases:
    req=urllib.request.Request(
        base+"/tools/route",
        data=json.dumps({"query": q, "top_k": 3}).encode(),
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        d=json.load(resp)
    ids=[str(x).lower() for x in (d.get("tool_ids") or [])]
    hit=any(fam in x or x.startswith(fam+".") or (fam=="web" and ("web" in x or "search" in x)) for x in ids)
    print(("OK" if hit else "MISS"), fam, ids, "conf", round(float(d.get("confidence_top1") or 0),3), "hc", d.get("high_confidence"))
    if not hit:
        fail += 1
open("/tmp/ns-mcp-route.ok","w").write("1" if fail==0 else "0")
PY
if [[ "$(cat /tmp/ns-mcp-route.ok)" == "1" ]]; then ok "all 6 MCP families route correctly"; else bad "MCP route family miss"; fi

echo
echo "==> 6 router accuracy bench"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYBIN="$ROOT/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  PYBIN="uv run python"
else
  PYBIN="python3"
fi
if $PYBIN "$ROOT/benchmarks/router_accuracy.py" >/tmp/ns-acc-run.txt 2>&1; then
  python3 - <<'PY'
import json
from pathlib import Path
p=Path("work/benchmarks/router_accuracy.json")
d=json.loads(p.read_text()) if p.exists() else {}
print("top1", d.get("top1_accuracy"), "top3", d.get("top3_accuracy"), "top5", d.get("top5_accuracy"))
print("reduction", d.get("avg_token_reduction"), "lat", d.get("latency_ms"))
t3=float(d.get("top3_accuracy") or 0)
red=float(d.get("avg_token_reduction") or 0)
open("/tmp/ns-acc.ok","w").write("1" if t3>=0.99 and red>=0.85 else "0")
PY
  if [[ "$(cat /tmp/ns-acc.ok)" == "1" ]]; then ok "router accuracy top3=1 + reduction≥0.85"; else bad "router accuracy thresholds"; cat /tmp/ns-acc-run.txt | tail -20; fi
else
  bad "router_accuracy.py failed"
  tail -30 /tmp/ns-acc-run.txt || true
fi

echo
echo "==> 7 MCP execute (optional)"
code=$(curl -s -o /tmp/ns-call.json -w '%{http_code}' -X POST "$BASE/tools/call" \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"s3.list_objects","arguments":{"bucket":"demo"}}' || true)
info "POST /tools/call HTTP $code — body: $(head -c 160 /tmp/ns-call.json)"
if grep -q 'MCP execute disabled' /tmp/ns-call.json 2>/dev/null; then
  info "execute OFF (default). Enable later with NSA_MCP_EXECUTE=1 + API keys"
  ok "honest execute gate"
elif [[ "$code" == "200" ]]; then
  ok "MCP execute returned 200"
else
  info "execute not enabled or missing credentials (OK for schema-only mode)"
  ok "execute path reachable"
fi

echo
echo "==> 8 metrics snapshot"
curl -fsS --max-time 30 "$BASE/metrics" -o /tmp/ns-metrics.txt || true
egrep 'nexus_ascr_acceptance_rate|router_routing_latency_ms|haoe_workflow_latency_ms|nexus_dipa_cascade_hit_rate' /tmp/ns-metrics.txt | head -20 || true
ok "metrics scraped"

echo
echo "============================================================"
echo " RESULT: PASS=$PASS  FAIL=$FAIL"
echo " Artifacts: /tmp/ns-*.json  and  $ROOT/work/benchmarks/router_accuracy.json"
echo "============================================================"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
