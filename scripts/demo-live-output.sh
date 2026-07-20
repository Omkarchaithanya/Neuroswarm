#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "======== docker compose ps ========"
docker compose ps
echo
echo "======== GET /health (proxy :80) ========"
curl -sS http://127.0.0.1/health | python3 -m json.tool
echo
echo "======== GET /ready ========"
curl -sS http://127.0.0.1/ready | python3 -m json.tool
echo
echo "======== POST /v1/chat/completions ========"
curl -sS http://127.0.0.1/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "messages":[{"role":"user","content":"In one short paragraph: what is NeuroSwarm-Arm and why run it on Arm Axion?"}],
    "max_tokens":180,
    "temperature":0.2,
    "agent_role":"reasoning"
  }' | python3 -m json.tool
echo
echo "======== tools/route sample ========"
curl -sS http://127.0.0.1/tools/route \
  -H 'Content-Type: application/json' \
  -d '{"query":"Search the web and summarize GitHub issues"}' | python3 -m json.tool | head -80
echo
echo "======== done ========"
