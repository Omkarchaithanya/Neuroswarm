---
type: domain
title: Coding Domain
description: Implementation conventions for NEXUS-ARM kernels and connectors
tags: [domain, coding]
id: nexus.domains.coding
timestamp: 2026-07-16T00:00:00Z
mount:
  agents: [coding]
  domains: [coding]
---

# Coding Domain

## Conventions

- Prefer kernel packages under `neuroswarm_arm/runtime/{haoe,dipa,router,aqr,awpp,maks,rtg,armcascade,okf}`
- Agents never call inference backends directly — go through DIPA
- Tool schemas: Semantic Router first; load OKF tool docs after route (ADR-0003)
- Institutional knowledge lives in `okf/`; episodic memory in Mem0 only (ADR-0002)
- Tests: `pytest tests/runtime/<kernel> -q`

## Related

- Architecture map: `/domains/architecture/domain.md`
- Deploy Compose: `/domains/deploy/docker.md`
- Chat DAG: `/playbooks/chat-cascade.md`
