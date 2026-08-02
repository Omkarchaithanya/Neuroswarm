#!/usr/bin/env bash
set -euo pipefail
IMG="${NSA_LLAMA_IMAGE:-nexus-arm/llama-kleidiai:server}"
docker run --rm --entrypoint llama-server "$IMG" -h 2>&1 | grep -iE 'draft|spec|model-draft|cont-batch|parallel|threads|ctx' | head -80
