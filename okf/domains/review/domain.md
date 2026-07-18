---
type: domain
title: Review Domain
description: Security and quality review playbooks
tags: [domain, review]
id: nexus.domains.review
timestamp: 2026-07-16T00:00:00Z
mount:
  agents: [reviewer]
---

# Review Domain

## Checklist

- No secrets in commits; firewall stays `/32` for demos
- Cascade regressions: use incident playbook before blaming models
- Mem0 must not contain OKF institutional text (ADR-0002)
- Tool docs only after routing (ADR-0003)
- Helm/Compose health: `/health` and `/ready` both green

## Related

- Incident: `/playbooks/incident-cascade.md`
- Cost: `/policies/cost-budget.md`
- GitHub: `/tools/github-mcp.md`
