#!/usr/bin/env bash
set -euo pipefail
BASE=http://127.0.0.1:9090/prometheus
echo "=== targets health ==="
curl -sf "$BASE/api/v1/targets" -o /tmp/targets.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/targets.json"))
for t in d["data"]["activeTargets"]:
    j=t.get("labels",{}).get("job","")
    print(f"{t.get('health'):5} {j:25} {t.get('scrapeUrl')} err={(t.get('lastError') or '')[:120]}")
PY
echo "=== sample queries ==="
for q in 'up' 'glances_cpu' 'glances_mem' 'container_cpu_usage_seconds_total' 'nexus_performix_available'; do
  curl -sf --get "$BASE/api/v1/query" --data-urlencode "query=$q" -o /tmp/q.json || true
  python3 - <<PY
import json
d=json.load(open("/tmp/q.json"))
n=len(d.get("data",{}).get("result",[]))
print("$q", "series=", n)
PY
done
