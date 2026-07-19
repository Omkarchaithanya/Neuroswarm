#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
OUT=benchmarks/results/performix
PUB=docs/evidence/performix
mkdir -p "$OUT" "$PUB" work/llama-opt

echo "==> extract full /opt/llama tree from Kleidi image"
cid=$(docker create nexus-arm/llama-kleidiai:server)
rm -rf work/llama-opt/*
docker cp "$cid:/opt/llama/." work/llama-opt/
docker rm -f "$cid" >/dev/null
find work/llama-opt -type f | head -30
ls -la work/llama-opt/bin/ work/llama-opt/lib/ 2>/dev/null | head -40
WL="$(pwd)/work/llama-opt/bin/llama-server"
chmod +x "$WL" || true
file "$WL" || true
ldd "$WL" 2>&1 | head -20 || true

# Smoke: does instruction_mix accept a simple system binary?
echo "==> smoke instruction_mix on /usr/bin/python3.12"
set +e
apx recipe run instruction_mix --workload /usr/bin/python3.12 --timeout 25 --deploy-tools --json > /tmp/imix-py.jsonl 2>&1
RC=$?
set -e
tail -5 /tmp/imix-py.jsonl
echo "smoke_rc=$RC"
RUN=$(python3 - <<'PY'
import json,re
t=open("/tmp/imix-py.jsonl",encoding="utf-8",errors="replace").read()
for line in t.splitlines():
    line=line.strip()
    if not line.startswith("{"): continue
    try:
        d=json.loads(line)
    except Exception:
        continue
    rid=(d.get("data") or {}).get("run_id") or {}
    if isinstance(rid, dict) and rid.get("value"):
        print(rid["value"]); break
    m=re.search(r'"value"\s*:\s*"([0-9a-f]+)"', line)
    if m: print(m.group(1)); break
PY
)
echo "smoke_run=$RUN"
if [[ -n "$RUN" ]]; then
  rm -rf /tmp/apx-imix-py && mkdir -p /tmp/apx-imix-py
  apx run export "$RUN" /tmp/apx-imix-py --json 2>&1 | tail -5
  find /tmp/apx-imix-py -type f | head -20
fi

echo "==> instruction_mix on Kleidi llama-server with working-dir"
set +e
apx recipe run instruction_mix \
  --workload "$WL" \
  --working-dir "$(pwd)/work/llama-opt/bin" \
  --timeout 40 --deploy-tools --json > /tmp/imix-kleidi.jsonl 2>&1
RC2=$?
set -e
tail -8 /tmp/imix-kleidi.jsonl
echo "kleidi_rc=$RC2"
RUN2=$(python3 - <<'PY'
import json,re
t=open("/tmp/imix-kleidi.jsonl",encoding="utf-8",errors="replace").read()
for line in t.splitlines():
    line=line.strip()
    if not line.startswith("{"): continue
    try:
        d=json.loads(line)
    except Exception:
        continue
    rid=(d.get("data") or {}).get("run_id") or {}
    if isinstance(rid, dict) and rid.get("value"):
        print(rid["value"]); break
PY
)
echo "kleidi_run=$RUN2"
if [[ -n "$RUN2" ]]; then
  rm -rf /tmp/apx-imix-k && mkdir -p /tmp/apx-imix-k
  apx run export "$RUN2" /tmp/apx-imix-k --json 2>&1 | tail -5
  find /tmp/apx-imix-k -type f | head -30
  # Normalize if any content
  if [[ -f scripts/performix_normalize_export.py ]]; then
    python3 scripts/performix_normalize_export.py /tmp/apx-imix-k "$OUT/02-instruction_mix.json" "$RUN2" || true
  fi
  if [[ -f "$OUT/02-instruction_mix.json" ]]; then
    cp -f "$OUT/02-instruction_mix.json" "$PUB/"
    echo "PUBLISHED instruction_mix"
  fi
fi

# Always keep hotspots evidence honest
ls -la "$PUB" "$OUT" | head -40
test -f "$PUB/01-code_hotspots.json" -o -f "$OUT/01-code_hotspots.json" && echo HOTSPOTS_OK || echo HOTSPOTS_MISSING
test -f "$PUB/02-instruction_mix.json" -o -f "$OUT/02-instruction_mix.json" && echo IMIX_OK || echo IMIX_MISSING
