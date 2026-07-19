#!/usr/bin/env bash
# Capture judge-facing evidence from a live NeuroSwarm-Arm stack.
# Prefers `uv run` so benchmarks/run_all.py never silently skips on missing pydantic.
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RESULTS_DIR="${RESULTS_DIR:-$PROJECT_ROOT/benchmarks/results}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
METRICS_TOKEN="${NSA_RMF_METRICS_TOKEN:-}"

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

mkdir -p "$RESULTS_DIR" "$RESULTS_DIR/performix"
cd "$PROJECT_ROOT"

# Prefer proxy :80 if gateway :8000 not up.
if ! curl -fsS --max-time 3 "$BASE_URL/health" >/dev/null 2>&1; then
  if curl -fsS --max-time 3 "http://127.0.0.1/health" >/dev/null 2>&1; then
    BASE_URL="http://127.0.0.1"
  fi
fi

curl_auth() {
  local url="$1"
  local out="$2"
  shift 2 || true
  local args=(-fsS --max-time 120)
  if [[ -n "$METRICS_TOKEN" ]]; then
    args+=(-H "Authorization: Bearer ${METRICS_TOKEN}")
  fi
  curl "${args[@]}" "$@" "$url" -o "$out"
}

echo "==> health / ready @ $BASE_URL"
curl -fsS --max-time 30 "$BASE_URL/health" > "$RESULTS_DIR/health.json"
curl -fsS --max-time 30 "$BASE_URL/ready" > "$RESULTS_DIR/ready.json"

# Warm cascade so /metrics has counters (empty scrape is a known failure mode).
echo "==> warmup chat (populate RMF counters)"
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Warmup for metrics."}],"max_tokens":32,"temperature":0.1}' \
  "$BASE_URL/v1/chat/completions" > "$RESULTS_DIR/warmup-chat.json" || true
sleep 2

echo "==> /metrics"
METRICS_OK=0
for attempt in 1 2 3 4 5; do
  if curl_auth "$BASE_URL/metrics" "$RESULTS_DIR/prometheus-metrics.txt"; then
    # Reject empty / whitespace-only captures.
    if [[ -s "$RESULTS_DIR/prometheus-metrics.txt" ]] \
      && grep -qE '^[a-zA-Z_#]' "$RESULTS_DIR/prometheus-metrics.txt"; then
      METRICS_OK=1
      break
    fi
  fi
  echo "WARN: metrics empty/failed (attempt $attempt); retrying..." >&2
  sleep 3
done
if [[ "$METRICS_OK" != "1" ]]; then
  echo "ERROR: prometheus-metrics.txt still empty after retries" >&2
  # Best-effort: scrape from inside gateway container.
  GW="$("${DOCKER[@]}" compose ps -q gateway 2>/dev/null || true)"
  if [[ -n "$GW" ]]; then
    "${DOCKER[@]}" exec "$GW" curl -fsS http://127.0.0.1:8000/metrics \
      > "$RESULTS_DIR/prometheus-metrics.txt" 2>/dev/null || true
  fi
  if [[ ! -s "$RESULTS_DIR/prometheus-metrics.txt" ]]; then
    printf '# neuroswarm_metrics_capture_failed 1\n# HELP neuroswarm_metrics_capture_failed Capture could not scrape /metrics\n' \
      > "$RESULTS_DIR/prometheus-metrics.txt"
    echo "Wrote failure marker into prometheus-metrics.txt" >&2
  fi
fi

echo "==> tools/route + chat"
curl -fsS --max-time 60 -H 'Content-Type: application/json' \
  -d '{"query":"Search the web and summarize GitHub issues for the project"}' \
  "$BASE_URL/tools/route" > "$RESULTS_DIR/tools-route.json"
curl -fsS --max-time 300 -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Create a low-cost ARM inference demo plan."}],"max_tokens":256,"temperature":0.2}' \
  "$BASE_URL/v1/chat/completions" > "$RESULTS_DIR/chat-completion.json"

echo "==> benchmarks/run_all.py (uv preferred)"
run_all() {
  local py_cmd=("$@")
  PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "${py_cmd[@]}" benchmarks/run_all.py --out "$RESULTS_DIR/run_all.json"
}

if command -v uv >/dev/null 2>&1; then
  if ! (cd "$PROJECT_ROOT" && uv run python benchmarks/run_all.py --out "$RESULTS_DIR/run_all.json"); then
    echo "WARN: uv run failed; trying python3 with PYTHONPATH" >&2
    run_all python3 || {
      printf '{"status":"error","reason":"run_all failed after uv and python3"}\n' > "$RESULTS_DIR/run_all.json"
      echo "ERROR: run_all failed" >&2
    }
  fi
elif python3 -c 'import pydantic' >/dev/null 2>&1; then
  run_all python3 || {
    printf '{"status":"error","reason":"run_all python3 failed"}\n' > "$RESULTS_DIR/run_all.json"
  }
else
  echo "Host missing uv and pydantic — installing pydantic via pip --user" >&2
  python3 -m pip install --user -q pydantic pyyaml >/dev/null 2>&1 || true
  if python3 -c 'import pydantic' >/dev/null 2>&1; then
    run_all python3 || true
  else
    printf '{"status":"error","reason":"install uv (uv sync --all-groups) then re-run capture-evidence.sh"}\n' \
      > "$RESULTS_DIR/run_all.json"
    echo "ERROR: cannot run benchmarks without uv/pydantic" >&2
  fi
fi

# Fail loud if still a silent skip stub.
if grep -q '"status"[[:space:]]*:[[:space:]]*"skipped"' "$RESULTS_DIR/run_all.json" 2>/dev/null; then
  echo "ERROR: run_all.json still skipped — fix host deps (uv sync --all-groups)" >&2
fi

"${DOCKER[@]}" compose ps > "$RESULTS_DIR/docker-compose-ps.txt"
"${DOCKER[@]}" compose logs --tail=300 > "$RESULTS_DIR/docker-compose.log"

# KleidiAI vs stock proof for judges.
{
  echo "=== compose images ==="
  "${DOCKER[@]}" compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}' 2>/dev/null \
    || "${DOCKER[@]}" compose ps
  echo
  echo "=== kleidiai gate ==="
  if grep -q 'llama-kleidiai' "$RESULTS_DIR/docker-compose-ps.txt"; then
    echo "PASS: KleidiAI image present"
  else
    echo "FAIL: KleidiAI image NOT present — run scripts/deploy-kleidiai-tiers.sh"
  fi
  if grep -q 'ggml-org/llama.cpp' "$RESULTS_DIR/docker-compose-ps.txt"; then
    echo "FAIL: stock ggml-org/llama.cpp still running"
  fi
} | tee "$RESULTS_DIR/kleidiai-runtime-gate.txt"

{
  uname -m
  lscpu 2>/dev/null || true
  numactl --hardware 2>/dev/null || echo "numactl unavailable"
  grep -E 'asimd|sve|sve2|i8mm|dotprod|bf16' /proc/cpuinfo 2>/dev/null | head -20 || true
} > "$RESULTS_DIR/01-axion-system-info.txt"

# Publish a judge-visible copy (benchmarks/results is gitignored).
EVIDENCE_PUB="${PROJECT_ROOT}/docs/evidence/latest"
mkdir -p "$EVIDENCE_PUB"
cp -f "$RESULTS_DIR/health.json" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/ready.json" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/run_all.json" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/docker-compose-ps.txt" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/kleidiai-runtime-gate.txt" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/prometheus-metrics.txt" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/01-axion-system-info.txt" "$EVIDENCE_PUB/" 2>/dev/null || true
# chat/tools may contain long text — still useful for judges
cp -f "$RESULTS_DIR/chat-completion.json" "$EVIDENCE_PUB/" 2>/dev/null || true
cp -f "$RESULTS_DIR/tools-route.json" "$EVIDENCE_PUB/" 2>/dev/null || true

printf 'Evidence captured in %s (published copy: %s)\n' "$RESULTS_DIR" "$EVIDENCE_PUB"
