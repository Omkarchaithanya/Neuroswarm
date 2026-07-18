---
okf_version: "1.0"
type: concept
id: nexus.deploy.docker
title: Docker ARM64 Deploy
description: Dockerfile.arm64 and docker-compose for linux/arm64 gateway + tiers
tags: [deploy, docker, arm64, compose]
namespace: nexus.deploy
visibility: internal
status: approved
priority: 80
token_budget: 600
mount:
  agents: [planner, architect, coding]
  domains: [deploy]
ontology:
  class: Concept
  relations:
    - {pred: see_also, obj: nexus.deploy.axion}
    - {pred: see_also, obj: nexus.playbooks.deploy_axion}
timestamp: 2026-07-16T00:00:00Z
---

# Docker ARM64

## Image

```bash
docker buildx build --platform linux/arm64 \
  -f Dockerfile.arm64 \
  -t neuroswarm-arm-gateway:dev \
  --load .
```

CI builds the same image in `.github/workflows/ci.yml` (`docker-arm64` job).

## Compose

```bash
cp .env.example .env
docker compose --compatibility up --build -d
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

- File: `docker-compose.yaml`
- Gateway builds from `Dockerfile.arm64`
- Services set `platform: linux/arm64`
- Use `docker compose --compatibility up --build` so `deploy.resources` map to cgroup limits

## Bootstrap

On the Axion VM:

```bash
cd ~/neuroswarm-arm
bash scripts/bootstrap-vm.sh
```

## Health

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

## Docs

- `/docs/next-steps-axion.md`
- `/scripts/README.md`
