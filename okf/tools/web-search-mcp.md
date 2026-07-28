---
okf_version: "1.0"
type: tool
id: nexus.tools.web_search
title: Web Search MCP
description: Web search tool for research agents
resource: mcp://tools/web-search
tags: [tool, research, web]
aliases: [web-search, web_search]
namespace: nexus.tools
visibility: public
status: approved
priority: 65
token_budget: 300
mount:
  agents: [research]
  domains: [research]
timestamp: 2026-07-15T00:00:00Z
---

# Web Search MCP

Use for open-web fact gathering via SerpAPI (Google / News / Images / Scholar engines). Prefer institutional OKF docs when available.

Auth: `SERPAPI_API_KEY` (alias `SERP_API_KEY`).
