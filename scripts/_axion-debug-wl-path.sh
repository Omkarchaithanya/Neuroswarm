#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> file types"
file /tmp/llama-server-kleidi work/bin/llama-server-kleidi 2>/dev/null || true
ls -la /tmp/llama-server-kleidi work/bin/llama-server-kleidi 2>/dev/null || true
echo "==> extract with follow"
rm -f /tmp/llama-server-kleidi /tmp/llama-server-kleidi.bin
cid=$(docker create nexus-arm/llama-kleidiai:server)
docker cp "$cid:/opt/llama/bin/llama-server" /tmp/ls-raw
docker rm -f "$cid" >/dev/null
file /tmp/ls-raw
ls -la /tmp/ls-raw
# If symlink, resolve inside container
docker run --rm --entrypoint sh nexus-arm/llama-kleidiai:server -c 'ls -la /opt/llama/bin/llama-server; file /opt/llama/bin/llama-server; readlink -f /opt/llama/bin/llama-server; ls -la $(readlink -f /opt/llama/bin/llama-server) 2>/dev/null | head'
# Copy real binary via tar to preserve
docker run --rm --entrypoint tar nexus-arm/llama-kleidiai:server -C /opt/llama/bin -cf - llama-server | tar -C /tmp -xf -
ls -la /tmp/llama-server
file /tmp/llama-server
# apx target?
apx target list 2>&1 | head -40 || true
echo "==> env"
env | grep -iE 'PERFORMIX|APX|ARM_' || true
# Try instruction_mix with working-dir and relative name
cp -f /tmp/llama-server /home/tejaswini2482_gmail_com/neuroswarm-arm/llama-server-wl
chmod +x /home/tejaswini2482_gmail_com/neuroswarm-arm/llama-server-wl
cd /home/tejaswini2482_gmail_com/neuroswarm-arm
apx recipe run instruction_mix --workload ./llama-server-wl --working-dir "$(pwd)" --timeout 40 --deploy-tools --json 2>&1 | tee /tmp/imix-try.txt | tail -30
