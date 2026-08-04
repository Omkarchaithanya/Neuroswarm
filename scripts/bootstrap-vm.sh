#!/usr/bin/env bash
set -euo pipefail

INSTANCE_NAME="${INSTANCE_NAME:-neuroswarm-axion}"
MODEL_DIR="${MODEL_DIR:-/models}"
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/neuroswarm-arm}"
RESULTS_DIR="${RESULTS_DIR:-$PROJECT_ROOT/benchmarks/results}"
DEMO_MODEL_SOURCE="${DEMO_MODEL_SOURCE:-}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd uname
require_cmd lscpu
require_cmd grep
require_cmd sudo
require_cmd curl

wait_for_http() {
  local url="$1"
  local label="$2"
  local tries="${3:-30}"
  local sleep_s="${4:-2}"
  local i code body
  for ((i = 1; i <= tries; i++)); do
    code="$(curl -sS -o /tmp/ns_wait_body.txt -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo FAIL)"
    body="$(head -c 120 /tmp/ns_wait_body.txt 2>/dev/null || true)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
    sleep "$sleep_s"
  done
  echo "Timed out waiting for $label at $url (last_code=$code body=${body:0:80})" >&2
  return 1
}

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "Expected ARM64 VM. Got $(uname -m)." >&2
  exit 1
fi

features="$(grep -E 'Features|flags' /proc/cpuinfo | head -n 1 || true)"
for feature in sve sve2 i8mm bf16; do
  if [[ "$features" != *"$feature"* ]]; then
    echo "Missing expected Axion CPU feature: $feature" >&2
    exit 1
  fi
done

mkdir -p "$RESULTS_DIR"
{
  uname -m
  lscpu
  grep -E 'asimd|sve|sve2|i8mm|dotprod|bf16' /proc/cpuinfo || true
} > "$RESULTS_DIR/01-axion-system-info.txt"

sudo apt-get update
# Ubuntu ARM ports package is docker-compose-v2 (provides `docker compose`).
sudo apt-get install -y git curl ca-certificates build-essential cmake clang libcurl4-openssl-dev docker.io docker-compose-v2
sudo usermod -aG docker "$USER"

require_cmd docker
if ! docker compose version >/dev/null 2>&1; then
  if ! sudo docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is not available after installation." >&2
    exit 1
  fi
fi

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

if [[ ! -d "$PROJECT_ROOT" ]]; then
  echo "Missing project directory: $PROJECT_ROOT" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_ROOT/.env.example" ]]; then
  echo "Missing project checkout or .env.example." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
cp -n .env.example .env
chmod +x scripts/*.sh
if grep -q '^GRAFANA_ADMIN_PASSWORD=$' .env; then
  grafana_password="neuroswarm-$(date +%s)"
  sed -i "s/^GRAFANA_ADMIN_PASSWORD=$/GRAFANA_ADMIN_PASSWORD=$grafana_password/" .env
  echo "Generated a local Grafana admin password in .env."
fi

sudo mkdir -p "$MODEL_DIR"
sudo chown "$USER:$USER" "$MODEL_DIR"

if [[ -n "$DEMO_MODEL_SOURCE" ]]; then
  bash scripts/prepare-models.sh --demo-source "$DEMO_MODEL_SOURCE"
fi

required_models=(
  "$MODEL_DIR/xLAM-2-1b-fc-r-Q4_0.gguf"
  "$MODEL_DIR/xLAM-2-3b-fc-r-Q4_0.gguf"
  "$MODEL_DIR/DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)

for model in "${required_models[@]}"; do
  if [[ ! -e "$model" ]]; then
    echo "Missing model file: $model" >&2
    echo "Run: bash scripts/prepare-models.sh --manifest models/manifest.example.yaml" >&2
    exit 1
  fi
done

# k3s Traefik often owns host :80; free it so Compose nginx is reachable.
if [[ -x scripts/free-host-port80-for-compose.sh ]]; then
  bash scripts/free-host-port80-for-compose.sh || true
fi

# --compatibility maps deploy.resources to cgroup limits on non-swarm Compose.
"${DOCKER[@]}" compose --compatibility up --build -d
"${DOCKER[@]}" compose ps

wait_for_http "http://127.0.0.1:8000/health" "gateway health" || exit 1
wait_for_http "http://127.0.0.1:8000/ready" "gateway readiness" || exit 1

# Refresh nginx upstream DNS after gateway recreate, then free :80 again if needed.
"${DOCKER[@]}" compose restart proxy 2>/dev/null || true
bash scripts/free-host-port80-for-compose.sh || true
sleep 2

if ! wait_for_http "http://127.0.0.1/health" "proxy health" 20 2; then
  echo "WARN: proxy :80 still unhealthy — re-free Traefik and recreate proxy" >&2
  bash scripts/free-host-port80-for-compose.sh || true
  "${DOCKER[@]}" compose up -d --force-recreate proxy
  wait_for_http "http://127.0.0.1/health" "proxy health" 30 2 || exit 1
fi
wait_for_http "http://127.0.0.1/ready" "proxy readiness" || exit 1

health_json="$(curl -fsS http://127.0.0.1:8000/health)"
ready_json="$(curl -fsS http://127.0.0.1:8000/ready)"
route_json="$(curl -fsS -H 'Content-Type: application/json' -d '{"query":"Search web and summarize repository issues"}' http://127.0.0.1:8000/tools/route)"
chat_json="$(curl -fsS -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Create a low-cost ARM inference demo plan."}]}' http://127.0.0.1:8000/v1/chat/completions)"
metrics_text="$(curl -fsS http://127.0.0.1:8000/metrics)"

bash scripts/capture-evidence.sh

# Optional Performix host path (skip with SKIP_PERFORMIX=1).
if [[ "${SKIP_PERFORMIX:-0}" != "1" ]] && [[ -x scripts/install-performix.sh ]]; then
  if ! command -v apx >/dev/null 2>&1; then
    echo "==> Installing Arm Performix (apx)"
    bash scripts/install-performix.sh || echo "WARN: install-performix failed (non-fatal)"
  fi
  if command -v apx >/dev/null 2>&1 && command -v crontab >/dev/null 2>&1; then
    CRON_LINE="*/2 * * * * cd $PROJECT_ROOT && NSA_PERFORMIX_ALLOW_DEMO=0 bash scripts/refresh-performix-snapshot.sh >>work/performix/refresh.log 2>&1"
    (crontab -l 2>/dev/null | grep -v refresh-performix-snapshot.sh; echo "$CRON_LINE") | crontab - || true
    echo "==> performix refresh cron installed"
  fi
fi

echo "$health_json"
echo "$ready_json"
echo "$route_json" >/dev/null
echo "$chat_json" >/dev/null
echo "$metrics_text" >/dev/null
echo "Bootstrap complete."
echo "Public API (axion): http://<AXION_EXTERNAL_IP>/"
echo "  Gateway:     http://<AXION_EXTERNAL_IP>/health  /ready  /v1/chat/completions"
echo "Observability (neuroswarm-obs):"
echo "  Prometheus:  http://<OBS_EXTERNAL_IP>/prometheus/"
echo "  Grafana:     http://<OBS_EXTERNAL_IP>/grafana/"
echo "Private loopback on axion: gateway :8000; OTEL :4317/:4318/:8889"
