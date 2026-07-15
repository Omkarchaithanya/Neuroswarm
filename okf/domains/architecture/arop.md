---
type: concept
title: AROP — Autonomic Runtime Optimization Plane
description: Plane 5 optimizer for NEXUS-ARM (not MAKS Layer 5)
tags: [arop, evolution, plane5]
resource: mcp://arop
timestamp: 2026-07-15T00:00:00Z
---

# AROP — Autonomic Runtime Optimization Plane

Plane 5 optimizer for NEXUS-ARM. **Not** NEXUS Layer 5 (MAKS).

- Package: `neuroswarm_arm/evolution/`
- API: `/arop/health`, `/arop/optimize`, `/arop/policies`, `/arop/rollback`
- Docs: `docs/arop/architecture.md`

Pipeline: Observe → … → Canary → Monitor → Rollback → Knowledge Update.

Performix = ObservationProvider. GEPA = ReflectionStrategy (propose only).
