#!/usr/bin/env bash
# AROP preflight — Axion honesty gates before live --apply.
# Usage: bash scripts/arop-preflight.sh [path/to/code_hotspots.json]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOTSPOTS="${1:-work/arop/performix/code-hotspots.json}"
ALLOW_DEMO="${NSA_PERFORMIX_ALLOW_DEMO:-0}"

echo "=== AROP preflight ==="

if [[ "$ALLOW_DEMO" != "0" && "$ALLOW_DEMO" != "false" && "$ALLOW_DEMO" != "False" ]]; then
  echo "FAIL: NSA_PERFORMIX_ALLOW_DEMO=$ALLOW_DEMO — must be 0 for live AROP" >&2
  exit 1
fi
echo "OK: NSA_PERFORMIX_ALLOW_DEMO=0"

if [[ ! -f "$HOTSPOTS" ]]; then
  echo "FAIL: hotspots file missing: $HOTSPOTS" >&2
  exit 1
fi

python3 - "$HOTSPOTS" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
src = str(data.get("source") or "")
if src != "apx":
    print(f"FAIL: snapshot source={src!r} (require source=apx)", file=sys.stderr)
    raise SystemExit(1)
print(f"OK: source=apx ({path})")

# Contamination gate (same rules as metrics_parser)
import re
hotspots = data.get("hotspots") or []
if not isinstance(hotspots, list) or not hotspots:
    print("FAIL: empty hotspots", file=sys.stderr)
    raise SystemExit(1)
unknown = sum(
    float(h.get("pct") or 0)
    for h in hotspots
    if isinstance(h, dict) and re.search(r"Unknown symbol\s*@\s*0x", str(h.get("function") or ""), re.I)
)
top = hotspots[0] if isinstance(hotspots[0], dict) else {}
top_fn = str(top.get("function") or "")
load = {"posix_fallocate", "fallocate", "mmap", "__mmap", "read"}
tokens = set(re.split(r"[^a-zA-Z0-9_]+", top_fn.lower()))
if unknown > 20.0:
    print(f"FAIL: contaminated — Unknown symbol @ 0x share {unknown:.2f}%", file=sys.stderr)
    raise SystemExit(1)
if tokens & {s.lower() for s in load}:
    print(f"FAIL: contaminated — top hotspot load-time syscall: {top_fn!r}", file=sys.stderr)
    raise SystemExit(1)
print(f"OK: not contaminated (top={top_fn!r} pct={top.get('pct')})")
PY

# Optional KleidiAI hint (non-fatal)
if docker compose ps 2>/dev/null | grep -q tier1; then
  if docker compose logs tier1 2>/dev/null | grep -qi kleidi; then
    echo "OK: KleidiAI mentioned in tier1 logs"
  else
    echo "WARN: no KleidiAI string in recent tier1 logs (informational)"
  fi
fi

echo "=== preflight PASS ==="
echo "Next: dry-run offline, then:"
echo "  python -m neuroswarm_arm.arop.evolve_cycle --apply --hotspots $HOTSPOTS ..."
