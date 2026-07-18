---
okf_version: "1.0"
type: concept
id: nexus.deploy.axion
title: GCP Axion VM Deploy
description: VM-first demo path on c4a Axion ARM64 with deploy-vm.ps1
tags: [deploy, axion, gcp, arm64]
namespace: nexus.deploy
visibility: internal
status: approved
priority: 85
token_budget: 700
mount:
  agents: [planner, architect]
  domains: [deploy]
ontology:
  class: Concept
  relations:
    - {pred: depends_on, obj: nexus.deploy.docker}
    - {pred: see_also, obj: nexus.playbooks.deploy_axion}
timestamp: 2026-07-16T00:00:00Z
---

# GCP Axion VM

Primary demo target: Ubuntu 24.04 ARM64 on GCP Axion (`c4a-standard-8`), Neoverse-V2.

## Checkout path

Always `~/neuroswarm-arm` (dash). Do not use `~/neuroswarm_arm`.

## One-shot from Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy-vm.ps1 `
  -ProjectId <project> -Zone us-central1-a -InstanceName neuroswarm-axion
```

Upload models separately before bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\upload-models.ps1
```

## Order

sync repo → upload GGUFs → validate → bootstrap → smoke/evidence

## Scripts

| Script | Role |
|--------|------|
| `bootstrap-gcp.ps1` | Project, firewall `/32`, VM |
| `sync-vm.ps1` | Copy repo to VM |
| `upload-models.ps1` | Real tier GGUFs + aliases |
| `validate-vm.sh` | Preflight |
| `bootstrap-vm.sh` | Docker Compose up |
| `capture-evidence.sh` | Health/metrics/bench artifacts |

## Docs

- `/docs/next-steps-axion.md`
- `/docs/gcp-axion-setup.md`
- `/scripts/README.md`
