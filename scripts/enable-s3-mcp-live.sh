#!/bin/bash
# Enable live S3 MCP on Axion gateway: boto3 + AWS env + reconcile + real list_objects.
set -euo pipefail
cd ~/neuroswarm-arm

echo "=== 1) AWS env presence (no secret values) ==="
python3 - <<'PY'
from pathlib import Path
vals = {}
for line in Path(".env").read_text(encoding="utf-8", errors="ignore").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip()
for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "NSA_MCP_EXECUTE"):
    v = vals.get(k, "")
    print(f"{k}: present={bool(v)} len={len(v)}")
if not vals.get("AWS_ACCESS_KEY_ID") or not vals.get("AWS_SECRET_ACCESS_KEY"):
    raise SystemExit("MISSING AWS keys in .env")
PY

echo "=== 2) Install boto3 in gateway ==="
docker compose exec -T gateway pip install -q "boto3>=1.35" "botocore>=1.35"
docker compose exec -T gateway python - <<'PY'
import importlib.util
import os
assert importlib.util.find_spec("boto3"), "boto3 not importable"
print("boto3_ok", bool(os.environ.get("AWS_ACCESS_KEY_ID")), "region", os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
PY

echo "=== 3) Resolve bucket (S3_BUCKET env, else ListBuckets) ==="
BUCKET=$(docker compose exec -T gateway python - <<'PY'
import os, sys
import boto3
from botocore.exceptions import ClientError
region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
explicit = (os.environ.get("S3_BUCKET") or os.environ.get("AWS_S3_BUCKET") or "").strip()
s3 = boto3.client("s3", region_name=region)
if explicit:
    try:
        s3.head_bucket(Bucket=explicit)
    except ClientError as e:
        print(f"S3_BUCKET head failed for {explicit}: {e}", file=sys.stderr)
        raise SystemExit("BAD_S3_BUCKET")
    print(explicit, flush=True)
    raise SystemExit(0)
try:
    buckets = s3.list_buckets().get("Buckets") or []
except ClientError as e:
    print(
        "ListBuckets denied and S3_BUCKET unset. "
        "Set S3_BUCKET=<your-bucket> in .env (IAM needs s3:ListBucket + s3:GetObject on that bucket).",
        file=sys.stderr,
    )
    print(e, file=sys.stderr)
    raise SystemExit("NEED_S3_BUCKET")
if not buckets:
    raise SystemExit("NO_BUCKETS")
names = [b["Name"] for b in buckets]
pick = next((n for n in names if any(x in n.lower() for x in ("neuro", "swarm", "axion"))), names[0])
print(pick, flush=True)
PY
)
BUCKET=$(echo "$BUCKET" | tr -d '\r' | awk 'NF{print}' | tail -1)
echo "Using bucket: $BUCKET"
if [ -z "$BUCKET" ] || [ "$BUCKET" = "NO_BUCKETS" ] || [ "$BUCKET" = "NEED_S3_BUCKET" ] || [ "$BUCKET" = "BAD_S3_BUCKET" ]; then
  echo "ERROR: set S3_BUCKET in .env to a bucket this IAM user can access"
  exit 1
fi

echo "=== 4) Reload / reconcile MCP ==="
curl -sS -m 60 -X POST http://127.0.0.1:8000/tools/reload -H 'Content-Type: application/json' -d '{}' | python3 - <<'PY'
import sys, json
d = json.load(sys.stdin)
m = d.get("mcp_reconcile") or {}
print("loaded", d.get("loaded"), "executable", m.get("tools_executable"))
print("discovered_by_server", m.get("discovered_by_server"))
print("skipped_missing_deps", m.get("skipped_missing_deps"))
print("discover_errors", m.get("discover_errors"))
if "s3" not in (m.get("discovered_by_server") or {}):
    raise SystemExit("S3 not discovered")
PY

echo "=== 5) Live s3.list_objects ==="
curl -sS -m 45 -X POST http://127.0.0.1:8000/tools/call \
  -H 'Content-Type: application/json' \
  -d "{\"tool_id\":\"s3.list_objects\",\"arguments\":{\"bucket\":\"$BUCKET\",\"prefix\":\"\",\"limit\":5}}" \
  | python3 - <<'PY'
import sys, json
d = json.load(sys.stdin)
print("ok", d.get("ok"), "error", d.get("error"))
r = d.get("result") or {}
print("isError", r.get("isError"))
sc = r.get("structuredContent") or {}
# FastMCP may nest under result
payload = sc.get("result") if isinstance(sc.get("result"), dict) else sc
if not payload:
    # text content fallback
    print("raw_keys", list(d.keys()), list(r.keys())[:10])
    print(json.dumps(d)[:800])
    if d.get("ok") is False or r.get("isError"):
        raise SystemExit("S3 call failed")
else:
    print("bucket", payload.get("bucket"))
    print("key_count", payload.get("key_count"))
    objs = payload.get("objects") or []
    print("sample_keys", [o.get("key") for o in objs[:5]])
if d.get("ok") is False or r.get("isError"):
    raise SystemExit("S3 call failed")
print("S3_LIVE_OK")
PY

echo "=== DONE ==="
