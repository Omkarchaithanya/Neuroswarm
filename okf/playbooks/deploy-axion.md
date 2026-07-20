---
okf_version: "1.0"
type: playbook
id: nexus.playbooks.deploy_axion
title: Deploy Axion Playbook
description: Sync, upload models, validate, bootstrap Compose on GCP Axion
tags: [playbook, deploy, axion]
namespace: nexus.playbooks
visibility: internal
status: approved
priority: 85
mount:
  agents: [planner, architect]
timestamp: 2026-07-16T00:00:00Z
---

# Deploy Axion Playbook

1. Restrict firewall to your public IP `/32` (`bootstrap-gcp.ps1`)
2. Sync repo to `~/neuroswarm-arm` (`sync-vm.ps1` / `deploy-vm.ps1`)
3. Upload real GGUFs (`upload-models.ps1`) or smoke symlink (`prepare-models.sh`)
4. SSH → `bash scripts/validate-vm.sh`
5. `bash scripts/bootstrap-vm.sh` (Compose `--compatibility`)
6. Smoke: `/health`, `/ready`, chat, `/tools/route`
7. Capture evidence (`capture-evidence.sh`)

See `/domains/deploy/axion.md` and `/docs/next-steps-axion.md`.
