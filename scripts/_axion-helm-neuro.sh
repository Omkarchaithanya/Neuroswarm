#!/usr/bin/env bash
# Time helm upgrade of existing release "neuro" (already on Axion k3s).
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=docs/evidence/latest/HELM-TIMING.md
mkdir -p docs/evidence/latest

kubectl get nodes | tee /tmp/helm-nodes.txt
helm list -a | tee /tmp/helm-list.txt

START=$(date +%s)
set +e
helm upgrade --install neuro ./helm/neuroswarm-arm \
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
  echo "- command: helm upgrade --install neuro ./helm/neuroswarm-arm (images local)"
  echo "- exit_code: $EC"
  echo "- wall_seconds: $SECS"
  echo "- target: <90s"
  echo "- met_target: $( [[ $EC -eq 0 && $SECS -le 90 ]] && echo yes || echo no )"
  echo
  echo "## nodes"
  echo '```'
  cat /tmp/helm-nodes.txt
  echo '```'
  echo
  echo "## helm list"
  echo '```'
  cat /tmp/helm-list.txt
  echo '```'
  echo
  echo "## log (tail)"
  echo '```'
  tail -60 /tmp/helm-timing.log
  echo '```'
  echo
  echo "Note: prior conflict used release name neuroswarm while existing release is neuro."
} | tee "$OUT"
echo "HELM_EC=$EC HELM_SECS=$SECS"
