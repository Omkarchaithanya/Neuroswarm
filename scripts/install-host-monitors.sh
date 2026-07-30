#!/usr/bin/env bash
# Install real htop + btop on the Axion host (idempotent).
# Usage: bash scripts/install-host-monitors.sh
set -euo pipefail

BTOP_VERSION="${BTOP_VERSION:-1.4.0}"

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E bash "$0" "$@"
    fi
    echo "error: run as root (or with sudo)" >&2
    exit 1
  fi
}

install_btop_fallback() {
  local arch raw btop_arch
  arch="$(uname -m)"
  case "${arch}" in
    aarch64|arm64) btop_arch=aarch64 ;;
    x86_64|amd64) btop_arch=x86_64 ;;
    *)
      echo "error: unsupported arch for btop fallback: ${arch}" >&2
      return 1
      ;;
  esac
  raw="$(mktemp -d)"
  trap 'rm -rf "${raw}"' RETURN
  curl -fsSL \
    "https://github.com/aristocratos/btop/releases/download/v${BTOP_VERSION}/btop-${btop_arch}-linux-musl.tbz" \
    -o "${raw}/btop.tbz"
  tar -xjf "${raw}/btop.tbz" -C "${raw}"
  install -m 0755 "${raw}/btop/bin/btop" /usr/local/bin/btop
  echo "installed /usr/local/bin/btop (v${BTOP_VERSION} ${btop_arch})"
}

need_root "$@"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends htop procps sysstat curl ca-certificates

if ! command -v btop >/dev/null 2>&1; then
  if apt-get install -y --no-install-recommends btop; then
    echo "installed btop via apt"
  else
    install_btop_fallback
  fi
else
  echo "btop already present: $(command -v btop)"
fi

echo
echo "=== NeuroSwarm host monitors ready ==="
echo "Host-wide (preferred for demos):"
echo "  htop"
echo "  btop"
echo
echo "Gateway container PID namespace only:"
echo "  docker compose exec gateway htop"
echo "  docker compose exec gateway btop"
echo
echo "Prometheus-facing sidecars (Axion):"
echo "  docker compose --profile hostmon up -d cadvisor glances glances-web"
echo "  curl -sS http://127.0.0.1:8088/metrics | head"
echo "  curl -sS http://127.0.0.1:61209/metrics | head"
echo "  Glances UI: http://127.0.0.1:61208/  (tunnel from laptop if needed)"
echo
htop --version 2>/dev/null || true
btop --version 2>/dev/null || true
