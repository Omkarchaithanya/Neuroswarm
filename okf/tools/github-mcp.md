---
okf_version: "1.0"
type: tool
id: nexus.tools.github
title: GitHub MCP
description: GitHub API tools for issues, PRs, and search
resource: mcp://tools/github
tags: [tool, github, scm]
aliases: [github, github-mcp]
namespace: nexus.tools
visibility: public
status: approved
priority: 70
token_budget: 400
mount:
  agents: [coding, research, reviewer]
  domains: [coding]
timestamp: 2026-07-15T00:00:00Z
---

# GitHub MCP

## Capabilities

- Search issues and pull requests
- Read repository metadata
- Create comments when authorized

## Params

- `repo`: repository slug
- `state`: issue state
- `limit`: result limit

## Notes

Full tool schema is injected by Semantic MCP Router after selection. This document is institutional usage guidance only.
