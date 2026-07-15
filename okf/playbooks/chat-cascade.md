---
okf_version: "1.0"
type: playbook
id: nexus.playbooks.chat_cascade
title: Chat Cascade Playbook
description: HAOE chat DAG with Mem0 then OKF then router then DIPA
tags: [playbook, chat, cascade]
namespace: nexus.playbooks
visibility: internal
status: approved
priority: 85
mount:
  agents: [planner, architect, coding]
timestamp: 2026-07-15T00:00:00Z
---

# Chat Cascade Playbook

1. NeuroMemory / Mem0Adapter recall (official Mem0 hybrid search + reflection/)
2. OKF institutional context mount
3. Semantic MCP route (schemas only)
4. OKF tool docs for top-K tools + merge_mem0_okf prompt assembly
5. KV session
6. DIPA cascade inference
7. Official Mem0 ``add(messages)`` extraction + typed remember_* + reflect()
8. KV checkpoint

Notes:
- Never write OKF docs into Mem0 (ADR-0002).
- Call sites use NeuroMemory / Mem0Adapter only — never ``mem0ai`` SDK.
- JSON store is emergency circuit-breaker only; Mem0 is primary.
