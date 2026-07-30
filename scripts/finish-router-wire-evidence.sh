#!/usr/bin/env bash
set -euo pipefail
cd /home/tejaswini2482_gmail_com/neuroswarm-arm
mkdir -p work/evidence/router-wire

python3 - <<'PY'
import json
from pathlib import Path
chat = json.loads(Path("work/evidence/router-wire/chat-response.json").read_text())
m = chat.get("metrics") or {}
art = {
  "source": "live_chat_metrics",
  "query": "Generate a presigned S3 URL to upload report.pdf to bucket demos",
  "tool_schemas_used": chat.get("tool_schemas_used"),
  "tool_schema_count": m.get("tool_schema_count"),
  "tool_confidence": m.get("tool_confidence"),
  "tier_used": chat.get("tier_used"),
  "cascade_start_tier": m.get("cascade_start_tier"),
  "cost_router_tier": m.get("cost_router_tier"),
  "cost_router_reason": m.get("cost_router_reason"),
  "schema_token_reduction": m.get("schema_token_reduction"),
  "content_preview": (chat.get("content") or "")[:200],
  "note": "schema_token_reduction came from RoutingResult on the live request — not invented.",
}
Path("work/evidence/router-wire/schema-tokens.json").write_text(json.dumps(art, indent=2))
print(json.dumps(art, indent=2))
assert float(m.get("schema_token_reduction") or 0) > 0
assert int(m.get("tool_schema_count") or 0) == 3
print("PASS schema artifact")
PY

echo "=== low-conf escalate probe ==="
set +e
curl -sf -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"xyzzy do the thing somehow"}],"max_tokens":32}' \
  > work/evidence/router-wire/chat-lowconf.json
RC=$?
set -e
echo "curl_rc=$RC size=$(wc -c < work/evidence/router-wire/chat-lowconf.json)"
python3 - <<'PY'
import json
from pathlib import Path
p = Path("work/evidence/router-wire/chat-lowconf.json")
raw = p.read_text(encoding="utf-8").strip()
if not raw:
    raise SystemExit("empty lowconf response")
d = json.loads(raw)
m = d.get("metrics") or {}
print("tier_used", d.get("tier_used"), "cost_router_tier", m.get("cost_router_tier"), "reason", m.get("cost_router_reason"), "tool_conf", m.get("tool_confidence"), "schemas", d.get("tool_schemas_used"))
tier = int(m.get("cost_router_tier") or d.get("tier_used") or 0)
conf = float(m.get("tool_confidence") or 0)
if conf < 0.42:
    assert tier >= 2, (tier, conf, m.get("cost_router_reason"))
print("PASS lowconf gate")
PY
echo ALL_EVIDENCE_OK
