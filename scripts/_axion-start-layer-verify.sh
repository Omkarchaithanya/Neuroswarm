#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/neuroswarm-arm"
sed -i 's/\r$//' scripts/layer-live-verify.sh || true
chmod +x scripts/layer-live-verify.sh
mkdir -p work/logs work/layer-verify
if systemctl is-active k3s >/dev/null 2>&1; then
  sudo systemctl stop k3s || true
else
  echo k3s_already_down
fi
docker compose --compatibility up -d 2>&1 | tail -25
for i in $(seq 1 40); do
  if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "healthy_$i"
    break
  fi
  sleep 3
done
BASE=http://127.0.0.1:8000
if curl -fsS --max-time 3 http://127.0.0.1/health >/dev/null 2>&1; then
  BASE=http://127.0.0.1
fi
echo "BASE=$BASE"
nohup bash scripts/layer-live-verify.sh "$BASE" >work/logs/layer-live-verify.log 2>&1 &
echo "verify_pid=$!"
sleep 5
tail -40 work/logs/layer-live-verify.log || true
