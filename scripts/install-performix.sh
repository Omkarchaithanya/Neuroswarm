#!/usr/bin/env bash
# Install Arm Performix CLI (apx) on Ubuntu ARM64 (Axion target).
# See: https://learn.arm.com/install-guides/performix/
set -euo pipefail

ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "Expected aarch64 host; got $ARCH" >&2
  exit 1
fi

DEB_URL="${PERFORMIX_DEB_URL:-https://artifacts.tools.arm.com/arm-performix/app/latest/linux/arm64/ArmPerformix-linux-arm64.deb}"
TMP="${TMPDIR:-/tmp}/ArmPerformix-linux-arm64.deb"

echo "Downloading Performix from $DEB_URL"
wget -O "$TMP" "$DEB_URL"
sudo apt-get update -y
sudo dpkg -i "$TMP" || sudo apt-get install -f -y
sudo apt-get install -f -y

APX_DIR="/opt/Arm Performix/assets/apx"
if [[ -x "$APX_DIR/apx" ]]; then
  sudo ln -sfn "$APX_DIR/apx" /usr/local/bin/apx
  echo "apx linked to /usr/local/bin/apx"
  apx version || true
else
  echo "apx binary not found under $APX_DIR — check package install" >&2
  exit 1
fi

# Prepare local target / agent so recipe runs do not fail with AGENT_NOT_DEPLOYED.
if [[ "${SKIP_APX_PREPARE:-0}" == "1" ]]; then
  echo "SKIP_APX_PREPARE=1 — skipping apx target prepare"
  exit 0
fi

echo "==> apx target prepare (0-arg only — do not pass 'local')"
set +e
OUT="$(apx target prepare 2>&1)"
PREP_RC=$?
set -e

if [[ ${PREP_RC:-1} -eq 0 ]]; then
  echo "apx target prepare: ok"
  echo "$OUT" | tail -n 20 || true
else
  echo "WARN: apx target prepare failed (recipes may return AGENT_NOT_DEPLOYED)." >&2
  echo "$OUT" | tail -n 40 >&2 || true
  if echo "$OUT" | grep -qiE 'license|login|authenticate|unauthorized|AGENT_NOT_DEPLOYED'; then
    echo "BLOCKER hint: Arm Performix login/license or agent deploy required." >&2
  fi
  echo "Re-run manually after login/license: apx target prepare" >&2
  # Non-fatal for install — refresh script will fail loudly when demo disallowed.
  exit 0
fi
# Best-effort agent deploy if the CLI exposes it.
if apx agent --help >/dev/null 2>&1; then
  set +e
  apx agent deploy 2>&1 | tail -n 20 || true
  set -e
fi
