#!/usr/bin/env bash
# Live proof: CostRouter → cascade tiers on Axion (real chat, no mocks).
set -euo pipefail
ROOT=/home/tejaswini2482_gmail_com/neuroswarm-arm
cd "$ROOT"
mkdir -p work/evidence/router-wire

GW=$(docker ps --format '{{.Names}}' | grep -E 'gateway' | head -1)
echo "gateway=$GW"

# Deploy updated Python modules into running gateway (code not volume-mounted for all paths).
# Prefer bind-mount neuroswarm_arm if present; else docker cp.
if docker inspect "$GW" --format '{{json .Mounts}}' | grep -q neuroswarm_arm; then
  echo "neuroswarm_arm is bind-mounted — host files apply after restart"
else
  for f in \
    neuroswarm_arm/runtime/router/cost_router.py \
    neuroswarm_arm/runtime/router/orchestration.py \
    neuroswarm_arm/runtime/router/live_mcp_index.py \
    neuroswarm_arm/runtime/router/factory.py \
    neuroswarm_arm/runtime/router/__init__.py \
    neuroswarm_arm/runtime/dipa/router/decision_engine.py \
    neuroswarm_arm/runtime/haoe/integration/chat.py \
    neuroswarm_arm/gateway.py
  do
    docker cp "$f" "$GW:/app/$f"
  done
fi
docker restart "$GW"
sleep 12

echo "=== tier health ==="
for p in 8081 8082 8083 8000; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$p/health" || echo fail)
  echo "port=$p http=$code"
done

QUERY='Generate a presigned S3 URL to upload report.pdf to bucket demos'
echo "=== chat query ==="
curl -sf -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"$QUERY\"}],\"max_tokens\":96}" \
  | tee work/evidence/router-wire/chat-response.json | python3 -m json.tool | head -80

echo "=== extract metrics ==="
python3 - <<'PY'
import json
from pathlib import Path
p = Path("work/evidence/router-wire/chat-response.json")
d = json.loads(p.read_text())
out = {
  "tier_used": d.get("tier_used"),
  "tool_schemas_used": d.get("tool_schemas_used"),
  "metrics": d.get("metrics"),
  "content_preview": (d.get("content") or "")[:240],
  "choices_preview": None,
}
if d.get("choices"):
  out["choices_preview"] = str(d["choices"][0].get("message", {}).get("content", ""))[:240]
Path("work/evidence/router-wire/summary.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
tools = d.get("tool_schemas_used") or []
assert isinstance(tools, list), tools
assert len(tools) <= 5, f"expected top-K tools not catalog dump: {len(tools)}"
text = d.get("content") or ""
if not text and d.get("choices"):
  text = d["choices"][0].get("message", {}).get("content") or ""
assert str(text).strip(), "empty model output"
print("PASS chat real output + tool count", len(tools))
PY

echo "=== measure schema tokens (static router) ==="
python3 - <<'PY'
import json
from pathlib import Path
from neuroswarm_arm.runtime.router import build_router, RouterConfig
from neuroswarm_arm.runtime.router.models import RouteContext

cfg = RouterConfig(enable_hot_reload=False, allow_hash=True)
# Use existing templates; avoid live MCP spawn in measure unless requested.
router = build_router(cfg, start_sync=False)
q = "Generate a presigned S3 URL to upload report.pdf to bucket demos"
ctx = RouteContext(agent_id="evidence", agent_role="tool_call", conversation_excerpt=q)
result = router.route(q, context=ctx, top_k=3)
block = router.prompt_block(result)
# Full catalog estimate
from neuroswarm_arm.runtime.router.tool_serializer import serialize_tools_for_prompt
all_scored = []
# Approximate: tokens from all registry tools vs top-k block
import json as _json
all_schemas = []
for t in router.registry.as_list():
    all_schemas.append({"name": t.name, "description": t.description, "params": t.params})
before = max(1, len(_json.dumps(all_schemas, separators=(",", ":"))) // 4)
after = max(1, len(block) // 4)
# Prefer RoutingResult counters when present
rb = int(getattr(result, "prompt_tokens_before", 0) or 0)
ra = int(getattr(result, "prompt_tokens_after", 0) or 0)
if rb > 0:
    before, after = rb, ra
reduction = 1.0 - (after / float(before))
art = {
  "query": q,
  "tools_indexed": router.registry.size(),
  "top_k": len(result.tool_names),
  "tool_names": list(result.tool_names),
  "confidence_top1": result.confidence_top1,
  "prompt_tokens_before": before,
  "prompt_tokens_after": after,
  "schema_token_reduction": round(reduction, 4),
  "note": "Measured on this host; do not claim 0.92 unless this number is ~0.92",
}
Path("work/evidence/router-wire/schema-tokens.json").write_text(json.dumps(art, indent=2))
print(json.dumps(art, indent=2))
PY

echo "=== gateway logs cost_router / tier ==="
docker logs "$GW" 2>&1 | grep -iE 'cost_router|cascade_start|tier_used|CostRouter' | tail -30 || true
echo DONE
