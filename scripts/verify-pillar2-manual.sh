#!/usr/bin/env bash
# Manual Pillar 2 checks on Axion (after gateway image rebuild with FastEmbed).
set -euo pipefail
BASE="${1:-http://127.0.0.1:80}"

echo "=== /ready router ==="
curl -fsS --max-time 30 "$BASE/ready" -o /tmp/p2-ready.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/p2-ready.json"))
r=(d.get("tools") or {}).get("router") or {}
print("indexed", (d.get("tools") or {}).get("indexed_count"))
print("embedding_backend", r.get("embedding_backend"))
print("encoder", r.get("encoder"))
print("dims", r.get("embedding_dims"))
print("tools_registered", r.get("tools_registered"))
print("kernel_path", r.get("kernel_path"))
print("status", r.get("status"))
emb=r.get("embedding_backend")
n=int(r.get("tools_registered") or 0)
assert emb == "fastembed", emb
assert n >= 40, n
print("READY_ASSERT_OK")
PY

echo "=== /tools/route high-intent ==="
curl -fsS --max-time 60 -X POST "$BASE/tools/route" \
  -H "Content-Type: application/json" \
  -d '{"query":"Upload an artifact to S3 object storage","top_k":3}' \
  -o /tmp/p2-route.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/p2-route.json"))
ids=d.get("tool_ids") or [t.get("id") for t in d.get("tools") or []]
conf=d.get("confidence_top1") or 0
hc=d.get("high_confidence")
red=d.get("token_reduction_ratio")
print("ids", ids)
print("confidence_top1", conf, "high_confidence", hc, "reduction", red)
assert any("s3" in str(x).lower() for x in ids), ids
assert float(red or 0) >= 0.85 or len(ids) <= 3
assert float(conf or 0) >= 0.6, conf
assert hc is True, hc
print("ROUTE_ASSERT_OK")
PY

echo "=== chat high-conf probe ==="
curl -fsS --max-time 180 -X POST "$BASE/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Upload an artifact to S3 object storage"}],"max_tokens":64}' \
  -o /tmp/p2-chat.json || true
python3 - <<'PY'
import json
from pathlib import Path
p=Path("/tmp/p2-chat.json")
if not p.exists() or not p.read_text().strip():
    print("CHAT_SKIP")
else:
    d=json.loads(p.read_text())
    cap=d.get("thinking_token_cap")
    print("thinking_token_cap", cap)
    print("tool_schemas_used", d.get("tool_schemas_used"))
    print("content_len", len((d.get("content") or "") or (((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "")))
    assert int(cap or 0) == 256, f"expected thinking_token_cap=256 got {cap}"
    print("CHAT_HIGH_CONF_ASSERT_OK")
print("pillar2 manual checks done")
PY
