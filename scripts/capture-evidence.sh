#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/neuroswarm-arm}"
RESULTS_DIR="${RESULTS_DIR:-$PROJECT_ROOT/benchmarks/results}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

mkdir -p "$RESULTS_DIR"
cd "$PROJECT_ROOT"

curl -fsS "$BASE_URL/health" > "$RESULTS_DIR/health.json"
curl -fsS "$BASE_URL/ready" > "$RESULTS_DIR/ready.json"
curl -fsS "$BASE_URL/metrics" > "$RESULTS_DIR/prometheus-metrics.txt"
curl -fsS -H 'Content-Type: application/json' \
  -d '{"query":"Search the web and summarize GitHub issues for the project"}' \
  "$BASE_URL/tools/route" > "$RESULTS_DIR/tools-route.json"
curl -fsS -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Create a low-cost ARM inference demo plan."}],"max_tokens":256,"temperature":0.2}' \
  "$BASE_URL/v1/chat/completions" > "$RESULTS_DIR/chat-completion.json"

if python3 -c 'import pydantic' >/dev/null 2>&1; then
  python3 benchmarks/run_all.py --out "$RESULTS_DIR/run_all.json"
else
  echo "Host python missing pydantic; installing minimal deps for local harness." >&2
  python3 -m pip install --user -q pydantic pyyaml >/dev/null 2>&1 || true
  if python3 -c 'import pydantic' >/dev/null 2>&1; then
    PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      python3 benchmarks/run_all.py --out "$RESULTS_DIR/run_all.json"
  else
    printf '{"status":"skipped","reason":"host pydantic unavailable"}\n' > "$RESULTS_DIR/run_all.json"
    echo "Skipped benchmarks/run_all.py; wrote skip stub." >&2
  fi
fi

"${DOCKER[@]}" compose ps > "$RESULTS_DIR/docker-compose-ps.txt"
"${DOCKER[@]}" compose logs --tail=300 > "$RESULTS_DIR/docker-compose.log"

{
  uname -m
  lscpu
  grep -E 'asimd|sve|sve2|i8mm|dotprod|bf16' /proc/cpuinfo || true
} > "$RESULTS_DIR/01-axion-system-info.txt"

printf 'Evidence captured in %s\n' "$RESULTS_DIR"
