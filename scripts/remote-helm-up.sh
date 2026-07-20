#!/usr/bin/env bash
# Build/load images into k3s and helm upgrade NeuroSwarm-Arm on Axion.
# Usage: bash scripts/remote-helm-up.sh
# Env: SKIP_BUILD=1 to skip docker build; REQUIRE_HEALTH=0 to soft-fail probe (default hard-fail).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

find scripts -name '*.sh' -print0 2>/dev/null | xargs -0 -r sed -i 's/\r$//' || true

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
if [[ ! -f "$KUBECONFIG" && -f /etc/rancher/k3s/k3s.yaml ]]; then
  export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl missing; run scripts/install-k3s-axion.sh first" >&2
  exit 1
fi
if ! command -v helm >/dev/null 2>&1; then
  echo "==> Installing helm"
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Avoid port conflicts with Compose stack on the same VM.
if command -v docker >/dev/null 2>&1; then
  echo "==> Stopping Compose gateway/tiers/proxy (obs VM untouched)"
  docker compose --compatibility stop gateway tier1 tier2 tier3 proxy qdrant 2>/dev/null || true
fi

GATEWAY_IMAGE="${GATEWAY_IMAGE:-neuroswarm-arm-gateway:dev}"
LLAMA_IMAGE="${LLAMA_IMAGE:-nexus-arm/llama-kleidiai:server}"
RELEASE="${RELEASE:-neuro}"
CHART="./helm/neuroswarm-arm"
MODELS_HOST_PATH="${MODELS_HOST_PATH:-/models}"
SKIP_BUILD="${SKIP_BUILD:-0}"
REQUIRE_HEALTH="${REQUIRE_HEALTH:-1}"

HELM_SETS=(
  --set "image.gateway=$GATEWAY_IMAGE"
  --set "image.llama=$LLAMA_IMAGE"
  --set "models.hostPath=$MODELS_HOST_PATH"
  --set "observability.enabled=false"
  --set "service.type=NodePort"
  --set "service.nodePort=30080"
  --set "work.hostPath=$ROOT/work"
  --set "okf.hostPath=$ROOT/okf"
  --set "qdrant.enabled=true"
  --set "env.NSA_MEM_QDRANT_URL=http://qdrant:6333"
)

if [[ "$SKIP_BUILD" != "1" ]]; then
  echo "==> Building gateway image (ARM64)"
  docker build -f Dockerfile.arm64 -t "$GATEWAY_IMAGE" .
else
  echo "==> SKIP_BUILD=1 — using existing $GATEWAY_IMAGE"
  if ! docker image inspect "$GATEWAY_IMAGE" >/dev/null 2>&1; then
    echo "ERROR: image $GATEWAY_IMAGE not found locally" >&2
    exit 1
  fi
fi

# Import into k3s containerd
echo "==> Importing images into k3s"
docker save "$GATEWAY_IMAGE" | sudo k3s ctr images import -

if docker image inspect "$LLAMA_IMAGE" >/dev/null 2>&1; then
  docker save "$LLAMA_IMAGE" | sudo k3s ctr images import - || true
else
  echo "WARN: $LLAMA_IMAGE not present locally; chart will use pullPolicy IfNotPresent"
fi

mkdir -p work/swarm work/performix work/okf-artifacts work/memory/qdrant
test -f .env || cp .env.example .env || true

echo "==> helm upgrade --install $RELEASE"
if ! helm upgrade --install "$RELEASE" "$CHART" "${HELM_SETS[@]}" --timeout 10m; then
  echo "==> helm retry (keep NodePort 30080)"
  helm upgrade --install "$RELEASE" "$CHART" "${HELM_SETS[@]}" --timeout 10m
fi

# Wait for gateway + qdrant only (tier2 may stay Pending on small Axion nodes).
echo "==> Waiting for gateway + qdrant rollouts"
kubectl rollout status deployment/"${RELEASE}-neuroswarm-arm-gateway" --timeout=180s || \
  kubectl rollout status deployment -l app.kubernetes.io/component=gateway --timeout=180s
if kubectl get deploy -l app.kubernetes.io/component=qdrant -o name 2>/dev/null | grep -q .; then
  kubectl rollout status deployment -l app.kubernetes.io/component=qdrant --timeout=180s
  # Mem0 init needs Qdrant up — bounce gateway once so provider is mem0 not json_emergency.
  echo "==> Restarting gateway after Qdrant ready (Mem0)"
  kubectl rollout restart deployment -l app.kubernetes.io/component=gateway
  kubectl rollout status deployment -l app.kubernetes.io/component=gateway --timeout=180s
fi

kubectl get pods -o wide
kubectl get svc | grep -E 'gateway|qdrant|NAME' || true

NODE_PORT="$(kubectl get svc -l app.kubernetes.io/component=gateway -o jsonpath='{.items[0].spec.ports[0].nodePort}' 2>/dev/null || true)"
if [[ -z "$NODE_PORT" ]]; then
  NODE_PORT=30080
fi
echo "==> Probing http://127.0.0.1:${NODE_PORT}/health"
for i in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${NODE_PORT}/health" >/dev/null; then
    echo "OK health"
    curl -fsS -X POST "http://127.0.0.1:${NODE_PORT}/workflows" \
      -H 'Content-Type: application/json' \
      -d '{"steps":["a","b"],"name":"k8s_smoke"}' | head -c 400 || true
    echo
    kubectl get hpa 2>/dev/null || true
    echo "remote-helm-up: success (NodePort $NODE_PORT)"
    exit 0
  fi
  sleep 3
done

echo "remote-helm-up: health probe FAILED" >&2
kubectl get pods -o wide
kubectl describe pods -l app.kubernetes.io/component=gateway | tail -40 || true
if [[ "$REQUIRE_HEALTH" == "0" ]]; then
  echo "REQUIRE_HEALTH=0 — continuing after failed probe" >&2
  exit 0
fi
exit 1
