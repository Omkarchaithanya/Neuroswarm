#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
OUT=benchmarks/results/performix
PUB=docs/evidence/performix
mkdir -p "$OUT" "$PUB"

echo "==> install python3-venv for instruction_mix"
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip
python3 -m venv /tmp/apx-venv-smoke && echo VENV_OK || echo VENV_FAIL
rm -rf /tmp/apx-venv-smoke

IMPL="$(pwd)/work/llama-opt/lib/libllama-server-impl.so"
[[ -f "$IMPL" ]] || IMPL="$(pwd)/work/llama-opt/bin/libllama-server-impl.so"
WL="$(pwd)/work/llama-opt/bin/llama-server"
# Ensure libs visible next to stub
export LD_LIBRARY_PATH="$(pwd)/work/llama-opt/lib:$(pwd)/work/llama-opt/bin:${LD_LIBRARY_PATH:-}"

echo "==> instruction_mix with python3.12 + venv fixed"
log=/tmp/imix-venv.jsonl
apx recipe run instruction_mix --workload /usr/bin/python3.12 --timeout 40 --deploy-tools --json >"$log" 2>&1 || true
tail -4 "$log"
run=$(python3 -c "
import json
t=open('$log',encoding='utf-8',errors='replace').read()
for line in t.splitlines():
    line=line.strip()
    if not line.startswith('{'): continue
    try: d=json.loads(line)
    except Exception: continue
    rid=(d.get('data') or {}).get('run_id') or {}
    if isinstance(rid, dict) and rid.get('value'):
        print(rid['value']); break
" 2>/dev/null || true)
echo "run=$run"
if [[ -n "$run" ]]; then
  rm -rf /tmp/apx-imix-venv; mkdir -p /tmp/apx-imix-venv
  apx run export "$run" /tmp/apx-imix-venv --json >/tmp/imix-export-venv.txt 2>&1 || true
  find /tmp/apx-imix-venv -type f | head -30
  python3 scripts/performix_normalize_export.py /tmp/apx-imix-venv "$OUT/02-instruction_mix.json" "$run" 2>/tmp/imix-norm.txt || true
  cat /tmp/imix-norm.txt || true
fi

# Also try Kleidi server-impl SO (real code)
if [[ ! -s "$OUT/02-instruction_mix.json" && -f "$IMPL" ]]; then
  echo "==> instruction_mix on libllama-server-impl.so"
  log=/tmp/imix-impl2.jsonl
  apx recipe run instruction_mix --workload "$IMPL" --working-dir "$(dirname "$IMPL")" --timeout 40 --deploy-tools --json >"$log" 2>&1 || true
  tail -4 "$log"
  run=$(python3 -c "
import json
t=open('$log',encoding='utf-8',errors='replace').read()
for line in t.splitlines():
    line=line.strip()
    if not line.startswith('{'): continue
    try: d=json.loads(line)
    except Exception: continue
    rid=(d.get('data') or {}).get('run_id') or {}
    if isinstance(rid, dict) and rid.get('value'):
        print(rid['value']); break
" 2>/dev/null || true)
  echo "run2=$run"
  if [[ -n "$run" ]]; then
    rm -rf /tmp/apx-imix-impl2; mkdir -p /tmp/apx-imix-impl2
    apx run export "$run" /tmp/apx-imix-impl2 --json || true
    python3 scripts/performix_normalize_export.py /tmp/apx-imix-impl2 "$OUT/02-instruction_mix.json" "$run" 2>/tmp/imix-norm2.txt || true
    cat /tmp/imix-norm2.txt || true
  fi
fi

cp -f "$OUT/01-code_hotspots.json" "$PUB/" 2>/dev/null || true
cp -f "$OUT/02-instruction_mix.json" "$PUB/" 2>/dev/null || true
cp -f work/performix/snapshot.json "$PUB/snapshot.json" 2>/dev/null || true
cp -f "$OUT/00-recipe-list.txt" "$PUB/" 2>/dev/null || true
{
  echo "# Performix evidence (Axion)"
  echo
  echo "- code_hotspots: $( [[ -f $PUB/01-code_hotspots.json ]] && echo OK || echo MISSING )"
  echo "- instruction_mix: $( [[ -f $PUB/02-instruction_mix.json ]] && echo OK || echo MISSING )"
  echo "- Requires: python3-venv on target for instruction_mix tool"
  echo "- snapshot.json source=apx when present"
} > "$PUB/README.md"
ls -la "$PUB"
echo "IMIX=$( [[ -s $PUB/02-instruction_mix.json ]] && echo OK || echo NO ) HOT=$( [[ -s $PUB/01-code_hotspots.json ]] && echo OK || echo NO )"
# Success if hotspots OK; prefer imix too
[[ -s "$PUB/01-code_hotspots.json" ]]
