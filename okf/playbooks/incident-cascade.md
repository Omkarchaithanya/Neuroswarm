---
okf_version: "1.0"
type: playbook
id: nexus.playbooks.incident_cascade
title: Incident Cascade Playbook
description: Triage cascade/tier failures and gateway readiness regressions
tags: [playbook, incident, cascade]
namespace: nexus.playbooks
visibility: internal
status: approved
priority: 80
mount:
  agents: [architect, planner, reviewer]
timestamp: 2026-07-16T00:00:00Z
---

# Incident Cascade Playbook

1. Check `/health` and `/ready` — distinguish liveness vs model readiness
2. `docker compose ps` / `kubectl get pods` — which tier OOM or crashloop
3. Inspect cascade hit rate and tier error metrics
4. Verify GGUF paths/aliases under `/models`
5. If tier3 thrashing: lower context, raise machine size, or retune ASCR thresholds
6. Capture evidence (`capture-evidence.sh`) before config changes
7. Rollback last AROP policy if evolution caused regression

See `/domains/architecture/arm-cascade.md`, `/metrics/cascade-hit-rate.md`.
