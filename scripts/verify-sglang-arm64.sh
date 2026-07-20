#!/usr/bin/env bash
# Verify lmsysorg/sglang image has linux/arm64 before claiming Arm Neoverse SGLang support.
set -euo pipefail
IMG="${NSA_SGLANG_IMAGE:-lmsysorg/sglang:latest}"
echo "Inspecting $IMG"
if ! command -v docker >/dev/null 2>&1; then
  echo "docker missing — skip pull; document pin manually"
  exit 0
fi
docker buildx imagetools inspect "$IMG" 2>&1 | tee /tmp/sglang-inspect.txt || \
  docker manifest inspect "$IMG" 2>&1 | tee /tmp/sglang-inspect.txt

if grep -qi 'arm64\|aarch64' /tmp/sglang-inspect.txt; then
  echo "PASS: arm64 present in manifest for $IMG"
  echo "Cite: Arm May 2026 Neoverse SGLang blog + SGLANG_USE_CPU_ENGINE=1"
  exit 0
fi
echo "FAIL: no arm64 in manifest — pin a multi-arch tag (e.g. v0.5.12-cu129-runtime)" >&2
exit 1
