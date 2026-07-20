---
okf_version: "1.0"
type: tool
id: nexus.tools.browser
title: Browser MCP
description: Headless browser tools via Playwright for web tasks
resource: mcp://tools/browser
tags: [tool, browser, research, web]
aliases: [browser, browser-mcp]
namespace: nexus.tools
visibility: public
status: approved
priority: 60
token_budget: 400
mount:
  agents: [research, coding]
  domains: [research]
timestamp: 2026-07-16T00:00:00Z
---

# Browser MCP

## Capabilities

- Navigate URLs, extract page text, capture screenshots
- Fill forms when explicitly authorized

## Params

- `url`: target URL
- `action`: navigate | extract | screenshot
- `selector`: optional CSS selector

## Notes

Template: `templates/mcp-servers/browser/`. Full schema injected after Semantic MCP routing (ADR-0003). Prefer web-search MCP for discovery, then browser for deep pages.
