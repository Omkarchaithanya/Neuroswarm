---
type: domain
title: Deploy Domain
description: ARM64 Docker Compose, Helm chart, and GCP Axion VM deployment
tags: [domain, deploy, docker, helm, axion]
id: nexus.domains.deploy
timestamp: 2026-07-16T00:00:00Z
mount:
  agents: [planner, architect]
---

# Deploy Domain

How to run NeuroSwarm-Arm on Arm Neoverse:

1. **VM-first (demo):** Docker Compose on GCP Axion — see `axion.md` + `docker.md`
2. **K8s:** Helm chart `helm/neuroswarm-arm` — see `helm.md`

Prefer Axion Compose for hackathon evidence; use Helm for cluster packaging. Upload GGUF models before bootstrap.
