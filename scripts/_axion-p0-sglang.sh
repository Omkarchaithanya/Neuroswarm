#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/verify-sglang-arm64.sh 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"
echo "==> verify-sglang-arm64"
bash scripts/verify-sglang-arm64.sh
echo "SGLANG_VERIFY_EXIT=$?"
