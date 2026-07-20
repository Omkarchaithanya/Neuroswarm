---
okf_version: "1.0"
type: playbook
id: nexus.playbooks.router_onboarding
title: Router Onboarding Playbook
description: Validate semantic MCP routing and post-route OKF tool docs
tags: [playbook, router, mcp]
namespace: nexus.playbooks
visibility: internal
status: approved
priority: 70
mount:
  agents: [coding, architect, research]
timestamp: 2026-07-16T00:00:00Z
---

# Router Onboarding Playbook

1. Confirm OKF tool nodes exist under `/tools/` for templates in use
2. Run `pytest tests/runtime/router -q`
3. Smoke `POST /tools/route` with a multi-tool query
4. Verify only Top-K schemas reach the prompt; OKF tool docs load after route (ADR-0003)
5. Optional: `python benchmarks/router_full.py`

See `/domains/architecture/router.md`.
