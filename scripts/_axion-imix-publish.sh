#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=benchmarks/results/performix
PUB=docs/evidence/performix
mkdir -p "$OUT" "$PUB"

# Latest successful instruction_mix export
EDIR=/tmp/apx-imix-impl2
if [[ ! -d "$EDIR" ]]; then EDIR=/tmp/apx-imix-venv; fi
echo "==> inspect $EDIR"
find "$EDIR" -type f | head -40
# Unzip if needed
for z in "$EDIR"/*.zip; do
  [[ -f "$z" ]] || continue
  unzip -l "$z" | head -40
  mkdir -p "$EDIR/unz"
  unzip -o -q "$z" -d "$EDIR/unz" || true
done
find "$EDIR" -type f \( -name '*.json' -o -name '*.csv' -o -name '*.txt' -o -name '*.svg' \) | head -50

# Build honest instruction_mix artifact from export (do not require hotspots)
python3 - <<'PY'
import json, zipfile, shutil
from pathlib import Path
from datetime import datetime, timezone

roots = [Path("/tmp/apx-imix-impl2"), Path("/tmp/apx-imix-venv")]
out = Path("benchmarks/results/performix/02-instruction_mix.json")
pub = Path("docs/evidence/performix")
pub.mkdir(parents=True, exist_ok=True)

def collect(root: Path):
    files = []
    if not root.exists():
        return files
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".json", ".csv", ".txt", ".svg", ".html"}:
            files.append(p)
        if p.is_file() and p.suffix.lower() == ".zip":
            dest = root / "unz"
            dest.mkdir(exist_ok=True)
            try:
                with zipfile.ZipFile(p) as z:
                    z.extractall(dest)
            except Exception as e:
                print("zip fail", p, e)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".json", ".csv", ".txt", ".svg", ".html"}:
            files.append(p)
    return files

chosen = None
payload = {
    "source": "apx",
    "recipe": "instruction_mix",
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "available": 1.0,
    "files": [],
    "summary": {},
    "raw_snippets": {},
}
for root in roots:
    files = collect(root)
    if not files:
        continue
    chosen = root
    for p in files[:40]:
        rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
        payload["files"].append(rel)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if p.suffix.lower() == ".json":
            try:
                data = json.loads(text)
                # Keep interesting keys
                if isinstance(data, dict):
                    for k in ("instruction_mix", "instructions", "simd", "neon", "sve", "categories", "summary", "metrics", "result"):
                        if k in data:
                            payload["summary"][k] = data[k]
                    payload["raw_snippets"][rel] = {kk: data[kk] for kk in list(data)[:30] if kk not in payload["summary"]}
            except Exception:
                payload["raw_snippets"][rel] = text[:2000]
        else:
            payload["raw_snippets"][rel] = text[:2000]
    break

if not chosen or not payload["files"]:
    print("NO_EXPORT_FILES")
    raise SystemExit(2)

out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
shutil.copy2(out, pub / out.name)
# also copy hotspots + snapshot
for name in ("01-code_hotspots.json", "00-recipe-list.txt", "snapshot.json"):
    src = Path("benchmarks/results/performix") / name
    alt = Path("work/performix/snapshot.json") if name == "snapshot.json" else src
    if alt.is_file():
        shutil.copy2(alt, pub / name)
    elif src.is_file():
        shutil.copy2(src, pub / name)
print("WROTE", out, "bytes", out.stat().st_size, "files", len(payload["files"]))
print("summary_keys", list(payload["summary"])[:20])
print("IMIX_ARTIFACT_OK")
PY

ls -la "$PUB"
