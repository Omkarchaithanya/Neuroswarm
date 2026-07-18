#!/usr/bin/env bash
# Attempt live apx prepare + recipe on Axion host; leave apx|unavailable snapshot.
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/*.sh 2>/dev/null || true
mkdir -p work/performix

echo "==> apx on PATH?"
if ! command -v apx >/dev/null 2>&1; then
  echo "apx missing — running install-performix.sh"
  bash scripts/install-performix.sh || true
fi
command -v apx || { echo "apx still missing"; NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh || true; exit 0; }

echo "==> apx target prepare (0-arg only)"
set +e
OUT="$(apx target prepare 2>&1)"
PREP_RC=$?
set -e
echo "$OUT" | tee work/performix/prepare.log | tail -n 40 || true
if [[ $PREP_RC -ne 0 ]]; then
  echo "WARN: apx target prepare failed (rc=$PREP_RC)" >&2
  if echo "$OUT" | grep -qiE 'license|login|authenticate|AGENT_NOT_DEPLOYED'; then
    echo "BLOCKER: license/login/agent — fix Arm Performix auth then re-run prepare" >&2
  fi
else
  echo "apx target prepare: ok"
fi
# Optional agent deploy only if subcommand exists.
if apx agent --help >/dev/null 2>&1; then
  set +e
  apx agent deploy 2>&1 | tee -a work/performix/prepare.log | tail -n 20
  set -e
fi

echo "==> manual recipe probe (timeout=60)"
set +e
apx recipe run code_hotspots --system-wide --timeout 60 --deploy-tools --json >work/performix/manual-run.ndjson 2>work/performix/apx.err
echo "manual_rc=$?"
set -e
tail -40 work/performix/apx.err 2>/dev/null || true
# Try export if run_id present even when rc!=0
RUN_ID="$(python3 - <<'PY'
import json, re
from pathlib import Path
text = Path("work/performix/manual-run.ndjson").read_text(encoding="utf-8", errors="replace")
text += "\n" + Path("work/performix/apx.err").read_text(encoding="utf-8", errors="replace") if Path("work/performix/apx.err").is_file() else ""
rid = None
for line in text.splitlines():
    line=line.strip()
    if not line: continue
    try:
        d=json.loads(line)
    except Exception:
        continue
    nest=(d.get("data") or {}) if isinstance(d, dict) else {}
    for blob in (d, nest):
        if not isinstance(blob, dict): continue
        v=blob.get("run_id")
        if isinstance(v, dict) and v.get("value"):
            rid=str(v["value"]); break
        if v: rid=str(v); break
    if rid: break
if not rid:
    m=re.search(r'"run_id"\s*:\s*\{\s*"value"\s*:\s*"([0-9a-fA-F]{8,})"', text)
    rid=m.group(1) if m else ""
print(rid or "")
PY
)"
if [[ -n "$RUN_ID" ]]; then
  echo "manual export run_id=$RUN_ID"
  EXPORT="$(mktemp -d)"
  set +e
  apx run export "$RUN_ID" "$EXPORT" --json 2>>work/performix/apx.err
  echo "export_rc=$?"
  set -e
  find "$EXPORT" -type f | head -20 || true
  rm -rf "$EXPORT"
fi

echo "==> refresh (fail-loud, duration=60)"
set +e
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 PERFORMIX_DURATION=60 bash scripts/refresh-performix-snapshot.sh
echo "refresh_rc=$?"
set -e
python3 - <<'PY'
import json
from pathlib import Path
p = Path("work/performix/snapshot.json")
print(json.loads(p.read_text()) if p.is_file() else "missing")
PY
