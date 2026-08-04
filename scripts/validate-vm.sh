#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/models}"
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/neuroswarm-arm}"

failures=0

section() {
  printf '\n== %s ==\n' "$1"
}

check() {
  local label="$1"
  shift
  if "$@"; then
    printf '[ok] %s\n' "$label"
  else
    printf '[fail] %s\n' "$label" >&2
    failures=$((failures + 1))
  fi
}

has_feature() {
  local feature="$1"
  grep -E 'Features|flags' /proc/cpuinfo | head -n 1 | grep -qw "$feature"
}

section "System"
uname -a
lscpu | sed -n '1,24p'
check "ARM64 architecture" test "$(uname -m)" = "aarch64"
for feature in sve sve2 i8mm bf16; do
  check "CPU feature: $feature" has_feature "$feature"
done

section "Disk"
df -h "$HOME" "$MODEL_DIR" 2>/dev/null || df -h "$HOME"

section "Project"
check "repo exists at $PROJECT_ROOT" test -d "$PROJECT_ROOT"
check ".env.example exists" test -f "$PROJECT_ROOT/.env.example"
check "docker-compose.yaml exists" test -f "$PROJECT_ROOT/docker-compose.yaml"
check "validate_kleidiai benchmark gate (median_tok_s)" \
  grep -q 'median_tok_s' "$PROJECT_ROOT/scripts/validate_kleidiai.py"
check "kleidiai baselines catalog" \
  test -f "$PROJECT_ROOT/benchmarks/kleidiai_baselines.json"

section "Runtime"
check "curl installed" command -v curl
check "python3 installed" command -v python3
check "docker installed" command -v docker
if command -v docker >/dev/null 2>&1; then
  docker --version || true
  if docker compose version >/dev/null 2>&1; then
    docker compose version
  elif sudo docker compose version >/dev/null 2>&1; then
    sudo docker compose version
  else
    printf '[fail] docker compose plugin available\n' >&2
    failures=$((failures + 1))
  fi
fi

section "Models"
required_models=(
  "$MODEL_DIR/xLAM-2-1b-fc-r-Q4_0.gguf"
  "$MODEL_DIR/xLAM-2-3b-fc-r-Q4_0.gguf"
  "$MODEL_DIR/DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)
for model in "${required_models[@]}"; do
  check "model exists: $model" test -e "$model"
done

section "Local Ports"
if command -v ss >/dev/null 2>&1; then
  echo "Public:"
  ss -ltnp | grep -E ':80\b' || true
  echo "Private loopback:"
  ss -ltnp | grep -E '127\.0\.0\.1:(8000|9090|3000)\b' || true
else
  printf 'ss not available; skipping port listing.\n'
fi

section "Summary"
if [[ "$failures" -gt 0 ]]; then
  printf 'VM validation completed with %s failure(s).\n' "$failures" >&2
  exit 1
fi

printf 'VM validation passed.\n'
