---
okf_version: "1.0"
type: concept
id: nexus.deploy.helm
title: Helm Chart Deploy
description: One-command Kubernetes install via helm/neuroswarm-arm
tags: [deploy, helm, kubernetes, arm64]
namespace: nexus.deploy
visibility: internal
status: approved
priority: 80
token_budget: 600
mount:
  agents: [planner, architect]
  domains: [deploy]
ontology:
  class: Concept
  relations:
    - {pred: see_also, obj: nexus.deploy.docker}
    - {pred: see_also, obj: nexus.playbooks.helm_install}
timestamp: 2026-07-16T00:00:00Z
---

# Helm Chart

## One-command install

```bash
bash scripts/deploy-k8s.sh
```

Or manually:

```bash
docker buildx build --platform linux/arm64 -f Dockerfile.arm64 -t neuroswarm-arm-gateway:dev --load .
docker buildx build --platform linux/arm64 -f docker/Dockerfile.llama-kleidiai -t nexus-arm/llama-kleidiai:server --load .
helm lint ./helm/neuroswarm-arm
helm upgrade --install neuro ./helm/neuroswarm-arm \
  --set image.gateway=neuroswarm-arm-gateway:dev \
  --set image.llama=nexus-arm/llama-kleidiai:server \
  --set models.hostPath=/models
```

Chart path: `helm/neuroswarm-arm/` (gateway, tier1/2/3, models PVC/hostPath, Prometheus/Grafana, optional SGLang).

## Values (key)

- `image.gateway` / `image.llama` / `image.pullPolicy`
- `models.hostPath` or PVC via `models.pvcSize`
- `tiers.tier1/2/3` model + resources
- `observability.enabled`
- `env.*` DIPA/KleidiAI toggles
- `sglangPrefill.enabled` (default false)

## Docs

- `helm/neuroswarm-arm/README.md`
- `/docs/inference/deployment.md`
