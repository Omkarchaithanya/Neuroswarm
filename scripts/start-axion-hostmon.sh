#!/usr/bin/env bash
set -euo pipefail
cd /home/tejaswini2482_gmail_com/neuroswarm-arm
sudo rm -rf ops/glances/glances.conf
sudo mkdir -p ops/glances
sudo tee ops/glances/glances.conf >/dev/null <<'CFG'
[global]
check_update=false
refresh=2

[prometheus]
host=0.0.0.0
port=9091
prefix=glances
labels=src:glances,host:axion

[raid]
disable=true

[folders]
disable=true

[sensors]
disable=true

[wifi]
disable=true

[irq]
disable=true
CFG
sudo chown -R tejaswini2482_gmail_com:tejaswini2482_gmail_com ops/glances

docker rm -f neuroswarm-cadvisor neuroswarm-glances 2>/dev/null || true

docker pull gcr.io/cadvisor/cadvisor:v0.52.1
docker pull nicolargo/glances:latest-full

docker run -d --name neuroswarm-cadvisor --restart unless-stopped \
  --privileged --pid=host \
  -e DOCKER_API_VERSION=1.44 \
  -v /:/rootfs:ro -v /var/run:/var/run:ro -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /sys:/sys:ro -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
  -v /var/lib/docker/:/var/lib/docker:ro -v /dev/disk/:/dev/disk:ro \
  -p 8088:8080 \
  --cpus=0.5 -m 256m \
  gcr.io/cadvisor/cadvisor:v0.52.1 \
  --housekeeping_interval=15s --docker_only=true \
  --docker=unix:///var/run/docker.sock --store_container_labels=true \
  --disable_metrics=advtcp,cpuset,hugetlb,memory_numa,referenced_memory,resctrl,sched,tcp,udp

docker run -d --name neuroswarm-glances --restart unless-stopped \
  --privileged --pid=host \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /etc/os-release:/etc/os-release:ro \
  -v /home/tejaswini2482_gmail_com/neuroswarm-arm/ops/glances/glances.conf:/glances/conf/glances.conf:ro \
  -e 'GLANCES_OPT=-q -C /glances/conf/glances.conf --disable-plugin raid,folders,sensors,wifi,irq --export prometheus --time 2' \
  -p 61209:9091 \
  --cpus=0.25 -m 128m \
  nicolargo/glances:latest-full

sleep 15
echo FILE=$(file ops/glances/glances.conf)
docker ps --filter name=neuroswarm-glances --filter name=neuroswarm-cadvisor --format '{{.Names}} {{.Status}} {{.Ports}}'
echo '--- glances ---'
curl -sf --max-time 5 http://127.0.0.1:61209/metrics | grep -E '^glances_(cpu_total|mem_percent|load)' | head -20 || docker logs neuroswarm-glances 2>&1 | tail -40
echo '--- cadvisor ---'
curl -sf --max-time 5 http://127.0.0.1:8088/healthz; echo
curl -sf --max-time 5 http://127.0.0.1:8088/metrics | grep -c '^container_cpu_usage_seconds_total' || docker logs neuroswarm-cadvisor 2>&1 | tail -20
