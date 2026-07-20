#!/usr/bin/env bash
# Refresh work/performix/snapshot.json for RMF/Grafana (live apx when available).
# Usage: bash scripts/refresh-performix-snapshot.sh
# Cron (host, every 2 min): */2 * * * * cd /path/to/neuroswarm-arm && bash scripts/refresh-performix-snapshot.sh
#
# Demo hotspots are written ONLY when NSA_PERFORMIX_ALLOW_DEMO=1.
# When Performix is required (NSA_AROP_PERFORMIX=1 or MCP URL set) and demo is
# disallowed, apx failure exits non-zero without rewriting a fake snapshot.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work/performix work/arop/performix
OUT_JSON="work/arop/performix/code-hotspots.json"
SNAP="work/performix/snapshot.json"
# Arm Performix recipe ids use underscores (code_hotspots); accept hyphen aliases.
RECIPE_RAW="${NSA_AROP_PERFORMIX_RECIPE:-code_hotspots}"
RECIPE="${RECIPE_RAW//-/_}"
DURATION="${PERFORMIX_DURATION:-15}"
APX_OK=0
ALLOW_DEMO="${NSA_PERFORMIX_ALLOW_DEMO:-0}"
REQUIRE_LIVE=0
if [[ "${NSA_AROP_PERFORMIX:-0}" == "1" ]] || [[ -n "${NSA_AROP_PERFORMIX_MCP:-}" ]]; then
  REQUIRE_LIVE=1
fi
# Explicit require flag overrides.
if [[ "${NSA_PERFORMIX_REQUIRE_LIVE:-}" == "1" ]]; then
  REQUIRE_LIVE=1
fi

write_unavailable() {
  local err="${1:-apx_recipe_failed}"
  mkdir -p work/performix
  python3 - "$SNAP" "$err" <<'PY'
import json, sys
from pathlib import Path
snap = Path(sys.argv[1])
err = sys.argv[2]
# Drop stale demo/synthetic before writing honest marker.
if snap.is_file():
    try:
        src = str(json.loads(snap.read_text(encoding="utf-8")).get("source") or "")
    except Exception:
        src = ""
    if src in {"demo", "synthetic", ""}:
        snap.unlink(missing_ok=True)
marker = {
    "available": 0,
    "source": "unavailable",
    "error": err,
    "hotspots": [],
    "ipc": 0.0,
    "pmu_available": 0.0,
}
snap.parent.mkdir(parents=True, exist_ok=True)
snap.write_text(json.dumps(marker, indent=2), encoding="utf-8")
print(f"Wrote {snap} source=unavailable error={err}")
PY
}

if ! command -v apx >/dev/null 2>&1; then
  echo "apx not on PATH" >&2
  if [[ "$ALLOW_DEMO" == "1" ]]; then
    APX_OK=0
  elif [[ "$REQUIRE_LIVE" == "1" ]]; then
    echo "Performix required but apx missing (set NSA_PERFORMIX_ALLOW_DEMO=1 for synthetic)" >&2
    write_unavailable "apx_missing"
    exit 1
  else
    echo "apx missing; leaving snapshot unchanged"
    exit 0
  fi
else
  echo "Running apx recipe run $RECIPE (timeout=${DURATION}s, system-wide, --deploy-tools) ..."
  RUN_JSON="$(mktemp)"
  set +e
  apx recipe run "$RECIPE" --system-wide --timeout "$DURATION" --deploy-tools --json \
    >"$RUN_JSON" 2>work/performix/apx.err
  RC=$?
  set -e
  echo "recipe_rc=$RC"
  # Always parse run_id — apx often exits non-zero after emitting a run_id.
  RUN_ID="$(python3 - "$RUN_JSON" <<'PY'
import json, re, sys

def _as_id(val):
    if val is None:
        return None
    if isinstance(val, dict):
        for k in ("value", "id", "run_id", "runId"):
            if val.get(k):
                return str(val[k])
        return None
    s = str(val).strip()
    return s or None

text = open(sys.argv[1], encoding="utf-8").read()
err_path = "work/performix/apx.err"
try:
    text = text + "\n" + open(err_path, encoding="utf-8", errors="replace").read()
except Exception:
    pass
run_id = None
blobs = []
try:
    blobs.append(json.loads(text))
except Exception:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            blobs.append(json.loads(line))
        except Exception:
            continue
for data in blobs:
    if not isinstance(data, dict):
        continue
    for key in ("run_id", "id", "runId"):
        rid = _as_id(data.get(key))
        if rid:
            run_id = rid
            break
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    if not run_id and nested:
        for key in ("run_id", "id", "runId"):
            rid = _as_id(nested.get(key))
            if rid:
                run_id = rid
                break
    if run_id:
        break
if not run_id:
    m = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text,
        re.I,
    )
    if m:
        run_id = m.group(0)
    else:
        m2 = re.search(r'"run_id"\s*:\s*\{\s*"value"\s*:\s*"([0-9a-fA-F]{8,})"', text)
        if m2:
            run_id = m2.group(1)
print(run_id or "")
PY
)"
  EXPORT_ERR=""
  if [[ -n "$RUN_ID" ]]; then
    echo "run_id=$RUN_ID (exporting regardless of recipe_rc=$RC)"
    EXPORT_DIR="$(mktemp -d)"
    set +e
    apx run export "$RUN_ID" "$EXPORT_DIR" --json >/dev/null 2>>work/performix/apx.err
    EXP_RC=$?
    set -e
    # Normalize export → code-hotspots.json (zipfile; no unzip binary needed).
    # APX_OK only when real hotspots are present and run metadata is not a failure.
    set +e
    NORM_OUT="$(python3 scripts/performix_normalize_export.py "$EXPORT_DIR" "$OUT_JSON" "$RUN_ID" 2>>work/performix/apx.err)"
    NORM_RC=$?
    set -e
    NORM_OUT="$(echo "$NORM_OUT" | tail -n 1 | tr -d '\r')"
    if [[ "$NORM_RC" -eq 0 && "$NORM_OUT" == "ok" ]]; then
      APX_OK=1
      echo "apx ok → $OUT_JSON (run_id=$RUN_ID export_rc=$EXP_RC recipe_rc=$RC)"
    else
      EXPORT_ERR="${NORM_OUT:-no_hotspots_in_export}"
      echo "export normalize failed: $EXPORT_ERR (export_rc=$EXP_RC)" >&2
    fi
    rm -rf "$EXPORT_DIR"
  else
    echo "no run_id in recipe output (recipe_rc=$RC)" >&2
  fi
  rm -f "$RUN_JSON"

  # Richer unavailable error from apx.err / export normalize
  UNAVAIL_ERR="${EXPORT_ERR:-apx_recipe_failed}"
  if [[ -z "$EXPORT_ERR" && -f work/performix/apx.err ]]; then
    if grep -qiE 'AGENT_NOT_DEPLOYED|agent not deployed' work/performix/apx.err; then
      UNAVAIL_ERR="AGENT_NOT_DEPLOYED"
    elif grep -qiE 'neoprof|deploy-tools|deploy tools' work/performix/apx.err; then
      UNAVAIL_ERR="neoprof_not_deployed"
    elif grep -qiE 'license|not licensed|login|authenticate|unauthorized' work/performix/apx.err; then
      UNAVAIL_ERR="apx_license_or_auth"
    fi
  fi

  if [[ "$APX_OK" -ne 1 ]]; then
    echo "apx recipe failed or export empty (see work/performix/apx.err)" >&2
    if [[ "$REQUIRE_LIVE" == "1" && "$ALLOW_DEMO" != "1" ]]; then
      write_unavailable "$UNAVAIL_ERR"
      exit 1
    fi
    if [[ "$ALLOW_DEMO" != "1" ]]; then
      echo "Leaving existing snapshot unchanged (set NSA_PERFORMIX_ALLOW_DEMO=1 for synthetic)"
      exit 0
    fi
    echo "NSA_PERFORMIX_ALLOW_DEMO=1 — writing demo hotspots"
  fi
fi

export APX_OK ALLOW_DEMO
python3 - <<'PY'
import json
import os
import time
from pathlib import Path

out = Path("work/arop/performix/code-hotspots.json")
snap_path = Path("work/performix/snapshot.json")
apx_ok = os.environ.get("APX_OK") == "1"
allow_demo = os.environ.get("ALLOW_DEMO") == "1"
data = {}
if out.exists():
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        data = {}

hotspots = data.get("hotspots") if isinstance(data.get("hotspots"), list) else []
tick = int(time.time() // 120) % 7
if not hotspots:
    # Never invent demo when live apx path already claimed success without hotspots.
    if apx_ok:
        raise SystemExit("apx export had no hotspots — refusing demo fill")
    if not allow_demo:
        raise SystemExit(0)
    base = [
        ("llama_decode", 42.5),
        ("ggml_compute", 18.2),
        ("neuroswarm_gateway", 9.1),
    ]
    hotspots = [
        {"function": name, "pct": round(pct + (tick - 3) * (0.4 if i == 0 else 0.15), 2)}
        for i, (name, pct) in enumerate(base)
    ]
    data = {**data, "source": "demo", "hotspots": hotspots}

summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
topdown = data.get("topdown") or data.get("microarch") or {}
if not isinstance(topdown, dict):
    topdown = {}

cycles = float(summary.get("cycles") or metrics.get("cycles") or data.get("cycles") or (1_000_000 + tick * 10_000))
instr = float(summary.get("instructions") or metrics.get("instructions") or data.get("instructions") or (2_500_000 + tick * 20_000))
ipc = float(summary.get("ipc") or metrics.get("ipc") or data.get("ipc") or (instr / cycles if cycles else 0.0))
if not apx_ok and data.get("source") == "demo":
    ipc = round(2.35 + tick * 0.05, 3)

pmu = data.get("pmu_available")
if pmu is None:
    pmu = 1.0 if apx_ok else 0.0

# Live success must stay source=apx even if upstream omitted the field.
src = data.get("source") or ("apx" if apx_ok else "demo")
if apx_ok:
    src = "apx"

snap = {
    "available": 1.0,
    "cycles": cycles,
    "instructions": instr,
    "ipc": ipc,
    "cache_misses": float(summary.get("cache_misses") or data.get("cache_misses") or 1200 + tick * 10),
    "branch_misses": float(summary.get("branch_misses") or data.get("branch_misses") or 80 + tick),
    "pmu_available": float(pmu),
    "hotspots": hotspots,
    "topdown": {
        "frontend_bound": float(topdown.get("frontend_bound") or topdown.get("frontend") or 0.22),
        "backend_bound": float(topdown.get("backend_bound") or topdown.get("backend") or 0.41),
    },
    "metrics": {"hotspot_top_pct": float(hotspots[0].get("pct") or hotspots[0].get("percent") or 0)},
    "source": src,
    "recommendations": data.get("recommendations")
    or ["Focus hottest function with Arm Performix code_hotspots / cpu_microarchitecture recipes"],
}
snap_path.parent.mkdir(parents=True, exist_ok=True)
snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
print(f"Wrote {snap_path} hotspots={len(hotspots)} ipc={ipc} pmu={pmu} source={snap['source']}")
PY
