#!/usr/bin/env bash
# Install k3s on Axion (single-node) for Helm primary runtime.
# Usage: bash scripts/install-k3s-axion.sh
set -euo pipefail

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "Expected aarch64 Axion host, got $(uname -m)" >&2
  exit 1
fi

if command -v kubectl >/dev/null 2>&1 && kubectl get nodes >/dev/null 2>&1; then
  echo "k3s/kubectl already usable"
  kubectl get nodes -o wide || true
  exit 0
fi

echo "==> Installing k3s (server)"
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 644" sh -

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$(id -u):$(id -g)" "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config" || true

# Convenience symlink for scripts that expect kubectl on PATH.
if ! command -v kubectl >/dev/null 2>&1; then
  sudo ln -sf /usr/local/bin/kubectl /usr/local/bin/kubectl 2>/dev/null || true
fi

echo "==> Waiting for node Ready"
for i in $(seq 1 60); do
  if kubectl get nodes 2>/dev/null | grep -q Ready; then
    kubectl get nodes -o wide
    echo "install-k3s-axion: success"
    exit 0
  fi
  sleep 2
done
echo "Timed out waiting for k3s node" >&2
exit 1
