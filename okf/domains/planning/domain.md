---
type: domain
title: Planning Domain
description: Task decomposition and workflow planning guidance
tags: [domain, planning]
id: nexus.domains.planning
timestamp: 2026-07-16T00:00:00Z
mount:
  agents: [planner, architect]
---

# Planning Domain

## Guidance

- Order: validate assumptions → sync/deploy → smoke → evidence → tune
- Prefer Axion Compose playbook for demos; Helm for cluster packaging
- Track SLIs: cascade hit rate, gateway p95, OKF token budget, thinking tokens
- Evolve via AROP only with approval gates (propose-only GEPA)

## Related

- Deploy: `/domains/deploy/`
- Playbooks: `/playbooks/deploy-axion.md`, `/playbooks/helm-install.md`
- Metrics: `/metrics/`
