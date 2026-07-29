#!/usr/bin/env bash
# Diagnose and fix missing tier ports 8081/8082/8083 on Axion VM.
# Usage: cd ~/neuroswarm-arm && bash scripts/tier_ports_fix.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

section() { printf '\n== %s ==\n' "$1"; }

tier_port_up() {
  local port="$1"
  curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1 \
    || curl -fsS --max-time 2 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
}

section "1. Port check (8081/8082/8083)"
PORTS_OK=0
for p in 8081 8082 8083; do
  if tier_port_up "$p"; then
    echo "  OK  :$p listening"
    PORTS_OK=$((PORTS_OK + 1))
  else
    echo "  FAIL:$p nothing listening"
  fi
done
if [[ "$PORTS_OK" -eq 3 ]]; then
  echo "All tier ports are up. No fix needed."
  exit 0
fi

section "2. Runtime mode"
K8S_ACTIVE=0
COMPOSE_ACTIVE=0
if command -v kubectl >/dev/null 2>&1; then
  if kubectl get pods -l app.kubernetes.io/name=neuroswarm-arm 2>/dev/null | grep -q Running; then
    K8S_ACTIVE=1
    echo "  k8s/Helm: ACTIVE (gateway on NodePort 30080, tiers are ClusterIP only)"
    kubectl get pods -l 'app in (tier1,tier2,tier3,gateway)' -o wide 2>/dev/null || kubectl get pods 2>/dev/null | head -20
  else
    echo "  k8s/Helm: not running"
  fi
else
  echo "  k8s/Helm: kubectl not installed"
fi

if "${DOCKER[@]}" compose ps tier1 tier2 tier3 2>/dev/null | grep -qE 'Up|running'; then
  COMPOSE_ACTIVE=1
  echo "  Docker Compose tiers: some containers up"
else
  echo "  Docker Compose tiers: NOT running"
fi
"${DOCKER[@]}" compose ps tier1 tier2 tier3 2>/dev/null || true

section "3. Model files (compose expects these names)"
bash scripts/ensure-compose-models.sh || {
  echo ""
  echo "ERROR: Could not prepare compose model symlinks."
  echo "Place GGUF files in /models, then re-run: bash scripts/tier_ports_fix.sh"
  exit 1
}
BEST_MODEL_DIR="$(grep -E '^MODEL_DIR=' .env | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
echo "  Using MODEL_DIR: $BEST_MODEL_DIR"

section "4. Fix"
if [[ "$K8S_ACTIVE" -eq 1 ]]; then
  echo "You are on k8s/Helm mode. Host ports 8081-8083 are NOT exposed in this mode."
  echo "Tiers only exist inside the cluster (ClusterIP)."
  echo ""
  if [[ "${TIER_PORTS_FIX_COMPOSE:-0}" != "1" ]]; then
    echo "Option A — use gateway (no 8081-8083 needed):"
    echo "  curl -fsS http://127.0.0.1:30080/health"
    echo "  bash scripts/smart_cascade_prompt.sh -m 512 \"your prompt\""
    echo ""
    echo "Option B — switch to Docker Compose (enables 8081-8083):"
    echo "  TIER_PORTS_FIX_COMPOSE=1 bash scripts/tier_ports_fix.sh"
    exit 2
  fi
  echo "TIER_PORTS_FIX_COMPOSE=1 — uninstalling Helm release and switching to Compose..."
  helm uninstall neuro 2>/dev/null || true
  sleep 3
fi

echo "Starting Docker Compose tiers..."
bash scripts/start-tiers-axion.sh

section "5. Verify"
for p in 8081 8082 8083; do
  if tier_port_up "$p"; then
    echo "  OK  :$p"
  else
    echo "  FAIL:$p — check: docker compose logs tier${p: -1} --tail 30"
    exit 1
  fi
done

echo ""
echo "PASS: tier ports 8081/8082/8083 are up."
echo "Test:"
echo "  bash scripts/tier_prompt.sh 1 \"What is 2+2?\" 64"
