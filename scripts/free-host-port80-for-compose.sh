#!/usr/bin/env bash
# Free host TCP :80 for Docker Compose nginx when k3s Traefik also claims it.
# Root cause: Traefik LoadBalancer + CNI hostPort DNAT wins for 127.0.0.1:80
# (Go "404 page not found"), so bootstrap's curl http://127.0.0.1/health never
# reaches Compose nginx.
#
# Usage: bash scripts/free-host-port80-for-compose.sh
# Env: KEEP_TRAEFIK=1 → skip (compose will use :8000 only)
set -euo pipefail

if [[ "${KEEP_TRAEFIK:-0}" == "1" ]]; then
  echo "KEEP_TRAEFIK=1 — leaving Traefik on :80"
  exit 0
fi

if ! command -v k3s >/dev/null 2>&1 && ! command -v kubectl >/dev/null 2>&1; then
  echo "No k3s/kubectl — nothing to free on :80"
  exit 0
fi

KUBECTL=(kubectl)
if ! kubectl get nodes >/dev/null 2>&1; then
  if [[ -f /etc/rancher/k3s/k3s.yaml ]]; then
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  fi
  if ! kubectl get nodes >/dev/null 2>&1; then
    if command -v k3s >/dev/null 2>&1 && sudo k3s kubectl get nodes >/dev/null 2>&1; then
      KUBECTL=(sudo k3s kubectl)
    else
      echo "kubectl not usable — skip Traefik free"
      exit 0
    fi
  fi
fi

# Is Traefik (or any k8s hostPort) answering :80 with non-nginx body?
PROBE="$(curl -sS -o /tmp/ns_p80.txt -w "%{http_code}" --max-time 3 http://127.0.0.1/health 2>/dev/null || echo FAIL)"
BODY="$(cat /tmp/ns_p80.txt 2>/dev/null || true)"
if [[ "$PROBE" == "200" ]] && echo "$BODY" | grep -q '"status"'; then
  echo "http://127.0.0.1/health already healthy (Compose or Ingress OK)"
  exit 0
fi

# Detect Traefik service / deployment
TRAEFIK_NS=""
if "${KUBECTL[@]}" get svc -n kube-system traefik >/dev/null 2>&1; then
  TRAEFIK_NS=kube-system
elif "${KUBECTL[@]}" get svc -A 2>/dev/null | grep -qE '[[:space:]]traefik[[:space:]]'; then
  TRAEFIK_NS="$("${KUBECTL[@]}" get svc -A -o json 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin)
for i in d.get("items") or []:
  if (i.get("metadata") or {}).get("name")=="traefik":
    print((i.get("metadata") or {}).get("namespace") or ""); break
' 2>/dev/null || true)"
fi

if [[ -z "${TRAEFIK_NS}" ]]; then
  echo "No Traefik service found; probe code=$PROBE body=${BODY:0:80}"
  exit 0
fi

echo "==> Freeing host :80 for Compose: scale Traefik → 0 in ns=$TRAEFIK_NS (k3s remains; use NodePort 30080 for Helm)"
# Scale deployment/daemonset if present
if "${KUBECTL[@]}" -n "$TRAEFIK_NS" get deploy traefik >/dev/null 2>&1; then
  "${KUBECTL[@]}" -n "$TRAEFIK_NS" scale deploy/traefik --replicas=0
elif "${KUBECTL[@]}" -n "$TRAEFIK_NS" get ds traefik >/dev/null 2>&1; then
  "${KUBECTL[@]}" -n "$TRAEFIK_NS" patch ds traefik -p '{"spec":{"template":{"spec":{"nodeSelector":{"traefik-disabled":"true"}}}}}' || true
fi

# Also patch Service away from LoadBalancer host exposure if still present
if "${KUBECTL[@]}" -n "$TRAEFIK_NS" get svc traefik >/dev/null 2>&1; then
  "${KUBECTL[@]}" -n "$TRAEFIK_NS" patch svc traefik --type=merge -p '{"spec":{"type":"ClusterIP","externalIPs":null}}' 2>/dev/null \
    || "${KUBECTL[@]}" -n "$TRAEFIK_NS" delete svc traefik --wait=false 2>/dev/null \
    || true
fi

# Wait for CNI hostPort to release
for i in $(seq 1 20); do
  sleep 1
  BODY2="$(curl -sS --max-time 2 http://127.0.0.1/health 2>/dev/null || true)"
  # Traefik gone → connection refused / empty / nginx / gateway JSON — not Go 404 page
  if [[ "$BODY2" != "404 page not found" ]]; then
    echo "Traefik host :80 released (attempt $i); body_prefix=${BODY2:0:60}"
    exit 0
  fi
done

echo "WARN: Traefik may still own :80 (body still Go 404). Compose proxy bind may race; retry after compose up." >&2
exit 0
