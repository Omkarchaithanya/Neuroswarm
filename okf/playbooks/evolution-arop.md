---
okf_version: "1.0"
type: playbook
id: nexus.playbooks.evolution_arop
title: Evolution AROP Playbook
description: Observe → reflect → propose → approve → write back to OKF sources
tags: [playbook, arop, gepa, evolution]
namespace: nexus.playbooks
visibility: internal
status: approved
priority: 70
mount:
  agents: [architect, planner]
timestamp: 2026-07-16T00:00:00Z
---

# Evolution AROP Playbook

1. Observe via Performix / metrics (ObservationProvider)
2. GEPA reflect — **propose only** (ADR propose-only reflection)
3. Human or gate approval of policy artifact
4. Write markdown under `okf/` sources via evolution sink (never into artifacts)
5. `uv run okf build --source okf --strict`
6. Canary → monitor → rollback if SLIs regress

See `/domains/architecture/arop.md`, `/domains/architecture/gepa.md`.
