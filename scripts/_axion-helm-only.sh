#!/usr/bin/env bash
# Time pure helm upgrade/install (no docker buildx) on existing k3s.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=docs/evidence/latest/HELM-TIMING.md
mkdir -p docs/evidence/latest

kubectl get nodes | tee /tmp/helm-nodes.txt
START=$(date +%s)
set +e
helm upgrade --install neuroswarm ./helm/neuroswarm-arm \
  --set image.pullPolicy=IfNotPresent \
  --set image.gateway=neuroswarm-arm-gateway:dev \
  --set image.llama=nexus-arm/llama-kleidiai:server \
  --wait --timeout 3m > /tmp/helm-timing.log 2>&1
EC=$?
set -e
END=$(date +%s)
SECS=$((END-START))
{
  echo "# Helm install timing (Axion k3s)"
  echo
  echo "- date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- command: helm upgrade --install neuroswarm ./helm/neuroswarm-arm (images already local)"
  echo "- exit_code: $EC"
  echo "- wall_seconds: $SECS"
  echo "- target: <90s"
  echo "- met_target: $( [[ $EC -eq 0 && $SECS -le 90 ]] && echo yes || echo partial_or_fail )"
  echo
  echo "## nodes"
  echo '```'
  cat /tmp/helm-nodes.txt
  echo '```'
  echo
  echo "## log (tail)"
  echo '```'
  tail -50 /tmp/helm-timing.log
  echo '```'
} | tee "$OUT"
echo "HELM_EC=$EC HELM_SECS=$SECS"
helm list -a 2>/dev/null | head -10 || true
