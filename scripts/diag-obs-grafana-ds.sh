#!/usr/bin/env bash
set -euo pipefail
echo "=== prometheus network peers ==="
docker network ls
PROM=$(docker ps --format '{{.Names}}' | grep -i prometheus | head -1)
GRAF=$(docker ps --format '{{.Names}}' | grep -i grafana | head -1)
echo "prom=$PROM graf=$GRAF"
docker inspect "$PROM" --format '{{json .NetworkSettings.Networks}}' | python3 -m json.tool | head -40
# Can Grafana resolve prometheus?
docker exec "$GRAF" wget -qO- --timeout=3 http://prometheus:9090/prometheus/api/v1/query?query=up 2>&1 | head -c 400 || true
echo
docker exec "$GRAF" wget -qO- --timeout=3 http://neuroswarm-arm-prometheus-1:9090/prometheus/api/v1/query?query=up 2>&1 | head -c 400 || true
echo
# List datasources via grafana API (anon may fail)
curl -sf http://127.0.0.1:3000/api/datasources 2>&1 | head -c 300 || true
echo
# After hostmon, recheck targets
BASE=http://127.0.0.1:9090/prometheus
curl -sf "$BASE/api/v1/targets" -o /tmp/t.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/t.json"))
for t in d["data"]["activeTargets"]:
    j=t.get("labels",{}).get("job","")
    if j in ("glances","cadvisor","neuroswarm-gateway","prometheus"):
        print(t.get("health"), j, t.get("scrapeUrl"), (t.get("lastError") or "")[:80])
PY
for q in 'glances_cpu_total' 'glances_mem_percent' 'up{job="glances"}' 'nexus_performix_available'; do
  curl -sf --get "$BASE/api/v1/query" --data-urlencode "query=$q" -o /tmp/q.json
  python3 -c 'import json,sys; d=json.load(open("/tmp/q.json")); print(sys.argv[1], len(d["data"]["result"]))' "$q"
done
