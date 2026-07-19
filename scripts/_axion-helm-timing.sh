#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=docs/evidence/latest/HELM-TIMING.md
mkdir -p docs/evidence/latest

if ! command -v helm >/dev/null || ! command -v kubectl >/dev/null; then
  echo "helm/kubectl missing" | tee "$OUT"
  exit 0
fi

kubectl get nodes 2>&1 | head -5 | tee /tmp/helm-nodes.txt
START=$(date +%s)
set +e
SKIP_BUILD=1 SKIP_LLAMA_BUILD=1 timeout 240 bash scripts/deploy-k8s.sh > /tmp/helm-timing.log 2>&1
EC=$?
set -e
END=$(date +%s)
SECS=$((END-START))
{
  echo "# Helm install timing (Axion)"
  echo
  echo "- date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- exit_code: $EC"
  echo "- wall_seconds: $SECS"
  echo "- target: <90s when images local (SKIP_BUILD=1 SKIP_LLAMA_BUILD=1)"
  echo "- met_target: $( [[ $EC -eq 0 && $SECS -le 90 ]] && echo yes || echo no )"
  echo
  echo "## kubectl nodes"
  echo '```'
  cat /tmp/helm-nodes.txt
  echo '```'
  echo
  echo "## tail log"
  echo '```'
  tail -40 /tmp/helm-timing.log
  echo '```'
} | tee "$OUT"
echo "HELM_EC=$EC HELM_SECS=$SECS"
