---
okf_version: "1.0"
type: tool
id: nexus.tools.slack
title: Slack MCP
description: Channel and DM messaging tools for agent notifications
resource: mcp://tools/slack
tags: [tool, slack, comms]
aliases: [slack, slack-mcp]
namespace: nexus.tools
visibility: public
status: approved
priority: 55
token_budget: 350
mount:
  agents: [coding, planner, research]
  domains: [coding]
timestamp: 2026-07-16T00:00:00Z
---

# Slack MCP

## Capabilities

- Post messages to channels or DMs
- Read recent thread context when authorized

## Params

- `channel`: channel ID or name
- `text`: message body
- `thread_ts`: optional thread parent

## Notes

Template: `templates/mcp-servers/slack/`. Full schema injected after Semantic MCP routing (ADR-0003).
