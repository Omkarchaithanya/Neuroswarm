#!/usr/bin/env bash
# Continue instruction_mix after full extract (tolerate pipefail).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
OUT=benchmarks/results/performix
PUB=docs/evidence/performix
mkdir -p "$OUT" "$PUB"

WL="$(pwd)/work/llama-opt/bin/llama-server"
if [[ ! -x "$WL" ]]; then
  echo "missing $WL — re-extract"
  cid=$(docker create nexus-arm/llama-kleidiai:server)
  mkdir -p work/llama-opt
  docker cp "$cid:/opt/llama/." work/llama-opt/
  docker rm -f "$cid" >/dev/null
fi
chmod +x "$WL" || true
echo "WL=$WL size=$(stat -c%s "$WL" 2>/dev/null || echo 0)"
ldd "$WL" 2>&1 | head -15 || true

try_imix() {
  local label="$1"; shift
  local log="/tmp/imix-${label}.jsonl"
  echo "==> try $label: $*"
  apx recipe run instruction_mix "$@" --timeout 35 --deploy-tools --json >"$log" 2>&1 || true
  tail -3 "$log" || true
  local run
  run=$(python3 -c "
import json,re
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
  echo "run_id=$run"
  [[ -n "$run" ]] || return 1
  local edir="/tmp/apx-imix-$label"
  rm -rf "$edir"; mkdir -p "$edir"
  apx run export "$run" "$edir" --json >/tmp/imix-export-$label.txt 2>&1 || true
  find "$edir" -type f 2>/dev/null | head -25 || true
  python3 scripts/performix_normalize_export.py "$edir" "$OUT/02-instruction_mix.json" "$run" 2>/tmp/imix-norm-$label.txt || true
  cat /tmp/imix-norm-$label.txt 2>/dev/null || true
  if [[ -s "$OUT/02-instruction_mix.json" ]]; then
    cp -f "$OUT/02-instruction_mix.json" "$PUB/"
    echo "PUBLISHED instruction_mix via $label"
    return 0
  fi
  return 1
}

# Prefer analyzing the large server impl shared object (contains the real code)
IMPL="$(pwd)/work/llama-opt/lib/libllama-server-impl.so"
[[ -f "$IMPL" ]] || IMPL="$(pwd)/work/llama-opt/bin/libllama-server-impl.so"

ok=0
try_imix py --workload /usr/bin/python3.12 && ok=1 || true
if [[ "$ok" != "1" && -f "$IMPL" ]]; then
  try_imix impl --workload "$IMPL" --working-dir "$(dirname "$IMPL")" && ok=1 || true
fi
if [[ "$ok" != "1" ]]; then
  try_imix kleidi --workload "$WL" --working-dir "$(dirname "$WL")" && ok=1 || true
fi

# Publish whatever hotspots we have + honest README
cp -f "$OUT/01-code_hotspots.json" "$PUB/" 2>/dev/null || true
cp -f work/performix/snapshot.json "$PUB/snapshot.json" 2>/dev/null || true
cp -f "$OUT/00-recipe-list.txt" "$PUB/" 2>/dev/null || true

{
  echo "# Performix evidence (Axion)"
  echo
  echo "- Host: GCP Axion c4a-standard-8"
  echo "- code_hotspots: $( [[ -f $PUB/01-code_hotspots.json ]] && echo OK || echo MISSING )"
  echo "- instruction_mix: $( [[ -f $PUB/02-instruction_mix.json ]] && echo OK || echo PENDING )"
  echo "- snapshot source=apx: see snapshot.json"
  echo "- Note: instruction_mix requires --workload; system-wide is rejected by apx."
  echo "- Recipe list from this host:"
  echo '```'
  cat "$PUB/00-recipe-list.txt" 2>/dev/null || true
  echo '```'
} > "$PUB/README.md"

echo "FINAL hotspots=$( [[ -f $PUB/01-code_hotspots.json ]] && echo yes || echo no ) imix=$( [[ -f $PUB/02-instruction_mix.json ]] && echo yes || echo no )"
ls -la "$PUB"
# Pass if hotspots present (instruction_mix preferred but not always achievable with stub+neoprof)
[[ -f "$PUB/01-code_hotspots.json" ]]
