---
okf_version: "1.0"
type: tool
id: nexus.tools.s3
title: S3 MCP
description: Object storage read/write tools for agent workflows
resource: mcp://tools/s3
tags: [tool, s3, storage]
aliases: [s3, s3-mcp]
namespace: nexus.tools
visibility: public
status: approved
priority: 60
token_budget: 400
mount:
  agents: [coding, planner]
  domains: [coding]
timestamp: 2026-07-16T00:00:00Z
---

# S3 MCP

## Capabilities

- List / get / put objects in configured buckets
- Prefetch model or evidence artifacts for deploy playbooks

## Params

- `bucket`: bucket name
- `key`: object key
- `prefix`: list prefix

## Notes

Template: `templates/mcp-servers/s3/`. Full schema injected after Semantic MCP routing (ADR-0003).
