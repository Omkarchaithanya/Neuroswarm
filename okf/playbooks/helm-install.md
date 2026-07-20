---
okf_version: "1.0"
type: playbook
id: nexus.playbooks.helm_install
title: Helm Install Playbook
description: Build ARM64 images and helm upgrade --install neuroswarm-arm
tags: [playbook, deploy, helm]
namespace: nexus.playbooks
visibility: internal
status: approved
priority: 75
mount:
  agents: [planner, architect]
timestamp: 2026-07-16T00:00:00Z
---

# Helm Install Playbook

1. Ensure kubectl context points at an ARM64-capable cluster (kind / k3s / Axion node)
2. Place GGUFs under `/models` (or set `MODELS_HOST_PATH`)
3. `bash scripts/deploy-k8s.sh` (builds gateway + llama, helm upgrade --install)
4. `kubectl port-forward svc/neuro-neuroswarm-arm-gateway 8000:8000`
5. Curl `/health` and `/ready`
6. Optional: port-forward Grafana `:3000` / Prometheus `:9090`

See `/domains/deploy/helm.md` and `helm/neuroswarm-arm/README.md`.
