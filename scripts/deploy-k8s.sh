#!/usr/bin/env bash
# One-command ARM64 build + Helm install for NeuroSwarm-Arm.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GATEWAY_IMAGE="${GATEWAY_IMAGE:-neuroswarm-arm-gateway:dev}"
LLAMA_IMAGE="${LLAMA_IMAGE:-nexus-arm/llama-kleidiai:server}"
RELEASE="${RELEASE:-neuro}"
CHART="./helm/neuroswarm-arm"
PLATFORM="${PLATFORM:-linux/arm64}"
MODELS_HOST_PATH="${MODELS_HOST_PATH:-/models}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SKIP_LLAMA_BUILD="${SKIP_LLAMA_BUILD:-0}"
KIND_CLUSTER="${KIND_CLUSTER:-}"

echo "==> NeuroSwarm-Arm K8s one-command deploy"
echo "    gateway=$GATEWAY_IMAGE llama=$LLAMA_IMAGE release=$RELEASE"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required" >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required" >&2
  exit 1
fi

docker buildx inspect >/dev/null 2>&1 || docker buildx create --use --name neuroswarm-arm-builder >/dev/null

if [[ "$SKIP_BUILD" != "1" ]]; then
  echo "==> Building gateway ($PLATFORM)"
  docker buildx build --platform "$PLATFORM" -f Dockerfile.arm64 -t "$GATEWAY_IMAGE" --load .
fi

if [[ "$SKIP_LLAMA_BUILD" != "1" ]]; then
  echo "==> Building llama KleidiAI server ($PLATFORM) — this can take a while"
  docker buildx build --platform "$PLATFORM" -f docker/Dockerfile.llama-kleidiai -t "$LLAMA_IMAGE" --load .
fi

if [[ -n "$KIND_CLUSTER" ]] || command -v kind >/dev/null 2>&1; then
  CLUSTER="${KIND_CLUSTER:-$(kind get clusters 2>/dev/null | head -n1 || true)}"
  if [[ -n "$CLUSTER" ]]; then
    echo "==> Loading images into kind cluster: $CLUSTER"
    kind load docker-image "$GATEWAY_IMAGE" --name "$CLUSTER"
    kind load docker-image "$LLAMA_IMAGE" --name "$CLUSTER"
  fi
fi

HELM_SET=(
  --set "image.gateway=$GATEWAY_IMAGE"
  --set "image.llama=$LLAMA_IMAGE"
  --set "image.pullPolicy=IfNotPresent"
)

if [[ -n "$MODELS_HOST_PATH" ]]; then
  HELM_SET+=(--set "models.hostPath=$MODELS_HOST_PATH")
fi

echo "==> helm upgrade --install $RELEASE $CHART"
helm upgrade --install "$RELEASE" "$CHART" "${HELM_SET[@]}"

echo "==> Waiting for gateway rollout"
kubectl rollout status "deployment/${RELEASE}-neuroswarm-arm-gateway" --timeout=300s || \
  kubectl rollout status deployment -l "app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=gateway" --timeout=300s

GW_SVC="${RELEASE}-neuroswarm-arm-gateway"
echo ""
echo "Deployed. Port-forward and smoke:"
echo "  kubectl port-forward svc/${GW_SVC} 8000:8000"
echo "  curl -fsS http://127.0.0.1:8000/health"
echo "  curl -fsS http://127.0.0.1:8000/ready"
if [[ -n "$MODELS_HOST_PATH" ]]; then
  echo ""
  echo "Models expected under hostPath: $MODELS_HOST_PATH"
fi
