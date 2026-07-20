---
okf_version: "1.0"
type: tool
id: nexus.tools.postgres
title: Postgres MCP
description: SQL query tools with safety wrapper for agent access
resource: mcp://tools/postgres
tags: [tool, postgres, data, sql]
aliases: [postgres, postgres-mcp]
namespace: nexus.tools
visibility: public
status: approved
priority: 65
token_budget: 400
mount:
  agents: [coding, research, planner]
  domains: [coding]
timestamp: 2026-07-16T00:00:00Z
---

# Postgres MCP

## Capabilities

- Read-only and guarded write SQL against configured databases
- Schema introspection for planning queries

## Params

- `sql`: statement text
- `limit`: row cap
- `database`: logical DB name

## Notes

Template: `templates/mcp-servers/postgres/`. Full schema injected by Semantic MCP Router after selection. This document is institutional usage guidance only (ADR-0003).
