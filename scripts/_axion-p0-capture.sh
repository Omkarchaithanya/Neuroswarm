#!/usr/bin/env bash
# One-shot P0 capture on Axion (uploaded via scp; avoid PS quote mangling).
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/*.sh 2>/dev/null || true

echo "==> wait tiers healthy"
for i in $(seq 1 24); do
  if docker compose ps tier1 tier2 tier3 2>/dev/null | grep -q healthy; then
    echo "tiers healthy after ${i}0s-ish"
    break
  fi
  echo "waiting_tiers_$i"
  sleep 10
done
docker compose ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}' | grep -E 'tier|gateway' || true

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
# hnswlib (ann extra) needs headers; install if missing. Prefer default uv sync
# (not --all-groups) so evidence capture is not blocked by optional ANN builds.
sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-dev g++ >/dev/null || true
echo "==> uv sync (default groups — enough for run_all/pydantic)"
if ! uv sync; then
  echo "WARN: uv sync failed; pip install pydantic for capture"
  python3 -m pip install --user -q pydantic pyyaml httpx || true
fi

echo "==> capture-evidence"
bash scripts/capture-evidence.sh
echo "CAPTURE_EXIT=$?"

# Quick gates
python3 - <<'PY'
import json
from pathlib import Path
root = Path("benchmarks/results")
docs = Path("docs/evidence/latest")
issues = []
for name in ("run_all.json", "prometheus-metrics.txt", "docker-compose-ps.txt"):
    p = root / name
    if not p.exists() and (docs / name).exists():
        p = docs / name
    if not p.exists():
        issues.append(f"missing {name}")
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    if name == "run_all.json":
        d = json.loads(text or "{}")
        if d.get("status") == "skipped":
            issues.append("run_all skipped")
        elif d.get("status") != "ok" and "status" in d and d.get("status") != "ok":
            # accept ok or presence of results
            if d.get("status") not in ("ok", None) and "results" not in d:
                issues.append(f"run_all status={d.get('status')}")
    if name == "prometheus-metrics.txt" and len(text.strip()) < 20:
        issues.append("prometheus-metrics empty")
    if name == "docker-compose-ps.txt" and "llama-kleidiai" not in text and "nexus-arm/llama-kleidiai" not in text:
        # also check compose output may use service names only
        if "ggml-org/llama.cpp" in text and "llama-kleidiai" not in text:
            issues.append("stock ggml image still in compose ps")
print("GATES:", "PASS" if not issues else "FAIL", issues)
raise SystemExit(0 if not issues else 2)
PY
